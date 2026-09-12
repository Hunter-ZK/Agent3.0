from __future__ import annotations

from sqlglot import exp
from sqlglot.schema import MappingSchema

from sql_pilot_engine.analysis.sql_parser import (
    SQLParser,
)

from sql_pilot_engine.dialects.sqlglot import (
    resolve_sqlglot_dialect,
)

from sql_pilot_engine.evidence.lineage import (
    ColumnLineageEvidence,
    DerivedLineageStatus,
    LineageEvidenceError,
    ProgramLineageEvidence,
    SQLGlotDerivedLineageAdapter,
    build_lineage_diff,
)

from sql_pilot_engine.evidence.program_metadata import (
    MetadataObjectRole,
    ProgramMetadataEvidence,
    TableMetadataResolution,
    TableResolutionStatus,
)

from sql_pilot_engine.metadata.models import (
    PhysicalColumnRef,
    TableMetadata,
)

from sql_pilot_engine.program.models import (
    SQLProgram,
    SQLStatement,
)


class LineageEvidenceResolver:
    """
    SQLProgram + ProgramMetadataEvidence
        ↓
    ProgramLineageEvidence

    这是正式 Lineage Evidence 的 orchestration 层。

    它本身不重新实现：

    - SQL parsing algorithm
    - Scope algorithm
    - Column lineage algorithm
    - Metadata identifier resolution

    它只负责把现有能力组合起来。
    """

    def __init__(
        self,
        *,
        parser: SQLParser | None = None,
        derived_adapter: (
            SQLGlotDerivedLineageAdapter
            | None
        ) = None,
    ) -> None:

        self._parser = (
            parser
            or SQLParser()
        )

        self._derived_adapter = (
            derived_adapter
            or SQLGlotDerivedLineageAdapter()
        )

    def resolve(
        self,
        program: SQLProgram,
        metadata_evidence: ProgramMetadataEvidence,
        *,
        dialect: str = "maxcompute",
    ) -> ProgramLineageEvidence:
        """
        构建整份 SQLProgram 的字段级 Lineage Evidence。

        主流程：

            Metadata Preconditions
                    ↓
            Source MappingSchema
                    ↓
            Statement-by-Statement
                    ↓
            SQLGlot Derived Lineage
                    ↓
            Projection → Target Column
                    ↓
            Declared / Derived Diff
        """

        sqlglot_dialect = (
            resolve_sqlglot_dialect(
                dialect
            )
        )

        # ==================================================
        # 1. READ SOURCE Metadata
        # ==================================================

        read_sources = (
            self._require_read_sources(
                metadata_evidence
            )
        )

        (
            source_schema,
            canonical_by_requested,
        ) = (
            self._build_source_schema(
                read_sources,
                dialect=(
                    sqlglot_dialect
                ),
            )
        )

        # ==================================================
        # 2. WRITE TARGET Metadata Index
        # ==================================================

        target_index = {
            resolution.requested_table:
                resolution

            for resolution
            in metadata_evidence.tables

            if (
                resolution.role
                is MetadataObjectRole
                .WRITE_TARGET
            )
        }

        results: list[
            ColumnLineageEvidence
        ] = []

        # ==================================================
        # 3. 每一条写入 Statement 独立处理
        # ==================================================

        for statement in (
            program.statements
        ):

            write_target = (
                statement.write_target
            )

            if write_target is None:
                continue

            requested_target = (
                write_target
                .table_name
                .strip()
                .lower()
            )

            target_resolution = (
                target_index.get(
                    requested_target
                )
            )

            target_metadata = (
                self._require_target_metadata(
                    statement=statement,
                    resolution=(
                        target_resolution
                    ),
                )
            )

            # ==================================================
            # 4. SQLStatement → Query AST
            # ==================================================

            query = self._statement_query(
                statement,
                dialect=dialect,
            )

            # ==================================================
            # 5. SQLGlot Derived Lineage
            #
            # 对 SELECT 每一个 projection：
            #
            # projection[0] → upstream[]
            # projection[1] → upstream[]
            # ...
            # ==================================================

            derived_projections = (
                self
                ._derived_adapter
                .derive_query(
                    query,
                    schema=source_schema,
                    dialect=dialect,
                )
            )

            # ==================================================
            # 6. Target Columns ↔ Projection Positions
            # ==================================================

            target_mapping = (
                self._map_target_columns(
                    statement=statement,

                    target_metadata=(
                        target_metadata
                    ),

                    projection_count=(
                        len(
                            derived_projections
                        )
                    ),
                )
            )

            derived_by_index = {
                item.projection_index:
                    item

                for item
                in derived_projections
            }

            # ==================================================
            # 7. 生成最终 ColumnLineageEvidence
            # ==================================================

            for mapping in (
                target_mapping
            ):

                target_column = (
                    target_metadata
                    .get_column(
                        mapping.column_name
                    )
                )

                if target_column is None:
                    raise LineageEvidenceError(
                        "Target column disappeared "
                        "from Metadata during "
                        "lineage resolution: "
                        f"{target_metadata.full_name}."
                        f"{mapping.column_name}"
                    )

                target_ref = (
                    PhysicalColumnRef(
                        table_full_name=(
                            target_metadata
                            .full_name
                        ),

                        column_name=(
                            target_column.name
                        ),
                    )
                )

                declared = tuple(
                    sorted(
                        target_column
                        .technical
                        .declared_upstream_columns,

                        key=(
                            _column_ref_sort_key
                        ),
                    )
                )

                # ==============================================
                # Static Partition
                #
                # PARTITION(dt='202609')
                #
                # 这种字段没有 SELECT projection，
                # 因此没有物理 upstream。
                # ==============================================

                if (
                    mapping.projection_index
                    is None
                ):

                    derived = ()

                    derived_status = (
                        DerivedLineageStatus
                        .NO_PHYSICAL_UPSTREAM
                    )

                    expression_sql = (
                        mapping.static_value
                    )

                    unresolved_sources = ()

                    error_message = None

                else:

                    projection = (
                        derived_by_index.get(
                            mapping
                            .projection_index
                        )
                    )

                    if projection is None:
                        raise LineageEvidenceError(
                            "Derived projection "
                            "is missing: "
                            f"statement="
                            f"{statement.index}, "
                            f"projection="
                            f"{mapping.projection_index}."
                        )

                    derived = (
                        self
                        ._canonicalize_upstream(
                            projection.upstream,

                            canonical_by_requested=(
                                canonical_by_requested
                            ),
                        )
                    )

                    derived_status = (
                        projection.status
                    )

                    expression_sql = (
                        projection.expression_sql
                    )

                    unresolved_sources = (
                        projection
                        .unresolved_sources
                    )

                    error_message = (
                        projection
                        .error_message
                    )

                diff = build_lineage_diff(
                    declared=declared,
                    derived=derived,
                    derived_status=(
                        derived_status
                    ),
                )

                results.append(
                    ColumnLineageEvidence(
                        target=target_ref,

                        declared_upstream=(
                            declared
                        ),

                        declared_status=(
                            target_column
                            .management
                            .lineage_confirmation_status
                        ),

                        derived_upstream=(
                            derived
                        ),

                        derived_status=(
                            derived_status
                        ),

                        diff=diff,

                        statement_index=(
                            statement.index
                        ),

                        projection_index=(
                            mapping
                            .projection_index
                        ),

                        expression_sql=(
                            expression_sql
                        ),

                        unresolved_sources=(
                            unresolved_sources
                        ),

                        error_message=(
                            error_message
                        ),
                    )
                )

        return ProgramLineageEvidence(
            columns=tuple(
                results
            )
        )

    # ======================================================
    # Metadata Preconditions
    # ======================================================

    @staticmethod
    def _require_read_sources(
        metadata_evidence: ProgramMetadataEvidence,
    ) -> tuple[
        TableMetadataResolution,
        ...,
    ]:
        """
        正式 Derived Lineage 不允许：

        - ABSENT source
        - AMBIGUOUS source
        - ERROR source

        因为这样产生的 physical lineage
        不能称为可信证据。
        """

        read_sources = tuple(
            item

            for item
            in metadata_evidence.tables

            if (
                item.role
                is MetadataObjectRole
                .READ_SOURCE
            )
        )

        blocked = tuple(
            item

            for item
            in read_sources

            if (
                item.status
                is not
                TableResolutionStatus
                .RESOLVED

                or item.metadata is None

                or item.canonical_table
                is None
            )
        )

        if blocked:

            detail = ", ".join(
                (
                    f"{item.requested_table}"
                    f"[{item.status.value}]"
                )

                for item
                in blocked
            )

            raise LineageEvidenceError(
                "Derived lineage requires "
                "resolved read-source Metadata: "
                f"{detail}"
            )

        return read_sources

    @staticmethod
    def _require_target_metadata(
        *,
        statement: SQLStatement,
        resolution: (
            TableMetadataResolution
            | None
        ),
    ) -> TableMetadata:
        """
        目标字段映射依赖 Target Metadata。

        没有目标 Metadata，
        projection[1] 就无法可靠知道
        最终对应哪一个物理目标字段。
        """

        if (
            resolution is None
            or (
                resolution.status
                is not
                TableResolutionStatus
                .RESOLVED
            )
            or resolution.metadata is None
        ):

            status = (
                resolution.status.value

                if resolution is not None

                else "missing"
            )

            target_name = (
                statement
                .write_target
                .table_name

                if statement.write_target
                is not None

                else "<none>"
            )

            raise LineageEvidenceError(
                "Lineage requires resolved "
                "write-target Metadata: "
                f"statement={statement.index}, "
                f"target={target_name!r}, "
                f"status={status}."
            )

        return resolution.metadata

    # ======================================================
    # Metadata → SQLGlot MappingSchema
    # ======================================================

    @staticmethod
    def _build_source_schema(
        resolutions: tuple[
            TableMetadataResolution,
            ...,
        ],
        *,
        dialect: str,
    ) -> tuple[
        MappingSchema,
        dict[str, str],
    ]:
        """
        注意这里使用 requested_table
        构造 SQLGlot Schema。

        原因：

            SQL AST 中看到的是 requested identity。

        例如 SQL 写：

            FROM loan_detail

        MetadataResolver 已经解析为：

            project_ods.loan_detail

        但是 SQLGlot qualification
        此时仍然需要找到：

            loan_detail

        所以：

            MappingSchema key
                = requested_table

            最终输出 Evidence
                = canonical_table

        两者通过 canonical_by_requested
        做转换。
        """

        if not resolutions:
            return (
                MappingSchema(
                    {},
                    dialect=dialect,
                ),
                {},
            )

        identity_depths = {
            len(
                item
                .requested_table
                .split(".")
            )

            for item
            in resolutions
        }

        # SQLGlot MappingSchema 是固定 nesting depth。
        #
        # 当前 V1 如果同一 Program 同时混用：
        #
        #     bare_table
        #     project.table
        #
        # 暂时明确报错。
        #
        # 不在这里写复杂 fallback。
        if len(identity_depths) > 1:
            raise LineageEvidenceError(
                "Derived lineage currently "
                "requires read-source table "
                "identifiers to use one "
                "consistent qualification depth. "
                f"Detected depths="
                f"{sorted(identity_depths)!r}."
            )

        mapping: dict = {}

        canonical_by_requested: dict[
            str,
            str,
        ] = {}

        for resolution in resolutions:

            assert (
                resolution.metadata
                is not None
            )

            assert (
                resolution.canonical_table
                is not None
            )

            requested = (
                resolution
                .requested_table
                .strip()
                .lower()
            )

            canonical = (
                resolution
                .canonical_table
                .strip()
                .lower()
            )

            columns = {
                column.name: (
                    column
                    .technical
                    .data_type
                    or None
                )

                for column
                in (
                    resolution
                    .metadata
                    .columns
                    .values()
                )
            }

            if not columns:
                raise LineageEvidenceError(
                    "Resolved source Metadata "
                    "contains no columns: "
                    f"{canonical!r}."
                )

            _insert_schema_table(
                mapping,
                table_name=requested,
                columns=columns,
            )

            canonical_by_requested[
                requested
            ] = canonical

        return (
            MappingSchema(
                mapping,
                dialect=dialect,
            ),
            canonical_by_requested,
        )

    # ======================================================
    # SQLStatement → Query
    # ======================================================

    def _statement_query(
        self,
        statement: SQLStatement,
        *,
        dialect: str,
    ) -> exp.Query:
        """
        SQLProgram 不保存 SQLGlot AST。

        Lineage 需要 AST 时，
        从稳定的 statement.normalized_sql
        重新解析。

        这可以避免 SQLProgram
        直接依赖第三方 AST Contract。
        """

        parsed = self._parser.parse(
            statement.normalized_sql,
            dialect=dialect,
        )

        if (
            not parsed.success
            or parsed.statement_count != 1
        ):
            raise LineageEvidenceError(
                "Unable to reparse "
                f"statement {statement.index}: "
                f"{parsed.error_message}"
            )

        expression = (
            parsed.first_statement
        )

        if expression is None:
            raise LineageEvidenceError(
                "Parsed statement has "
                "no AST expression."
            )

        if isinstance(
            expression,
            exp.Query,
        ):
            return expression.copy()

        if not isinstance(
            expression,
            exp.Insert,
        ):
            raise LineageEvidenceError(
                "Write statement is not "
                "an INSERT/query expression: "
                f"statement={statement.index}."
            )

        query = (
            expression.args.get(
                "expression"
            )
        )

        if not isinstance(
            query,
            exp.Query,
        ):
            raise LineageEvidenceError(
                "INSERT statement contains "
                "no query expression: "
                f"statement={statement.index}."
            )

        query = query.copy()

        # WITH 有时挂在 INSERT 上，
        # 而不是内部 SELECT 上。
        #
        # Lineage 必须保留完整 CTE DAG。
        statement_with = (
            expression.args.get(
                "with_"
            )
        )

        query_with = (
            query.args.get(
                "with_"
            )
        )

        if (
            statement_with is not None
            and query_with is None
        ):
            query.set(
                "with_",
                statement_with.copy(),
            )

        return query

    # ======================================================
    # INSERT projection → Target Column
    # ======================================================

    @staticmethod
    def _map_target_columns(
        *,
        statement: SQLStatement,
        target_metadata: TableMetadata,
        projection_count: int,
    ) -> tuple[
        "_TargetColumnMapping",
        ...,
    ]:
        """
        复用 Simulator 已经确认的 INSERT 语义：

            普通字段
                +
            动态分区字段

        按位置对应 SELECT projection。

        静态分区字段不占 SELECT projection。
        """

        write_target = (
            statement.write_target
        )

        if write_target is None:
            raise LineageEvidenceError(
                "Target mapping requires "
                "a write target."
            )

        ordered_columns = tuple(
            sorted(
                target_metadata
                .columns
                .values(),

                key=lambda column: (
                    column
                    .technical
                    .ordinal_position
                ),
            )
        )

        partition_fields = tuple(
            target_metadata
            .technical
            .partition_fields
        )

        partition_set = set(
            partition_fields
        )

        partition_bindings = {
            binding.name
            .strip()
            .lower():
                binding

            for binding
            in write_target.partition_spec
        }

        unknown_partitions = (
            set(partition_bindings)
            - partition_set
        )

        if unknown_partitions:
            raise LineageEvidenceError(
                "INSERT references partition "
                "fields absent from target "
                "Metadata: "
                f"{sorted(unknown_partitions)!r}."
            )

        static_partition_names = {
            name

            for (
                name,
                binding,
            )
            in partition_bindings.items()

            if not binding.is_dynamic
        }

        regular_names = tuple(
            column.name

            for column
            in ordered_columns

            if (
                column.name
                not in partition_set
            )
        )

        dynamic_partition_names = tuple(
            name

            for name
            in partition_fields

            if (
                name
                not in
                static_partition_names
            )
        )

        projected_target_names = (
            regular_names
            + dynamic_partition_names
        )

        if (
            len(projected_target_names)
            != projection_count
        ):
            raise LineageEvidenceError(
                "INSERT projection count "
                "does not match target "
                "Metadata. "
                f"statement={statement.index}, "
                f"target="
                f"{target_metadata.full_name!r}, "
                f"expected="
                f"{len(projected_target_names)}, "
                f"actual="
                f"{projection_count}."
            )

        mappings: dict[
            str,
            _TargetColumnMapping,
        ] = {}

        for (
            projection_index,
            column_name,
        ) in enumerate(
            projected_target_names
        ):

            mappings[
                column_name
            ] = (
                _TargetColumnMapping(
                    column_name=(
                        column_name
                    ),
                    projection_index=(
                        projection_index
                    ),
                )
            )

        for name in (
            static_partition_names
        ):

            binding = (
                partition_bindings[
                    name
                ]
            )

            mappings[
                name
            ] = (
                _TargetColumnMapping(
                    column_name=name,

                    projection_index=None,

                    static_value=(
                        binding.value
                    ),
                )
            )

        missing = {
            column.name

            for column
            in ordered_columns
        } - set(mappings)

        if missing:
            raise LineageEvidenceError(
                "Target columns cannot be "
                "mapped to INSERT output: "
                f"{sorted(missing)!r}."
            )

        return tuple(
            mappings[
                column.name
            ]

            for column
            in ordered_columns
        )

    # ======================================================
    # SQL requested identity → canonical physical identity
    # ======================================================

    @staticmethod
    def _canonicalize_upstream(
        upstream: tuple[
            PhysicalColumnRef,
            ...,
        ],
        *,
        canonical_by_requested: dict[
            str,
            str,
        ],
    ) -> tuple[
        PhysicalColumnRef,
        ...,
    ]:

        canonical: set[
            PhysicalColumnRef
        ] = set()

        for ref in upstream:

            table_name = (
                ref
                .table_full_name
                .strip()
                .lower()
            )

            canonical_name = (
                canonical_by_requested.get(
                    table_name,
                    table_name,
                )
            )

            canonical.add(
                PhysicalColumnRef(
                    table_full_name=(
                        canonical_name
                    ),

                    column_name=(
                        ref.column_name
                    ),
                )
            )

        return tuple(
            sorted(
                canonical,
                key=_column_ref_sort_key,
            )
        )


from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class _TargetColumnMapping:
    """
    一个目标字段如何从 INSERT 获得值。

    projection_index != None：
        值来自 SELECT projection。

    projection_index == None：
        值来自 static partition。
    """

    column_name: str

    projection_index: (
        int | None
    )

    static_value: (
        str | None
    ) = None


def _insert_schema_table(
    mapping: dict,
    *,
    table_name: str,
    columns: dict[
        str,
        str | None,
    ],
) -> None:
    """
    构造 SQLGlot MappingSchema
    所需的嵌套 mapping。

    table
        → {table: columns}

    project.table
        → {project: {table: columns}}

    catalog.project.table
        → {catalog: {project: {table: columns}}}
    """

    parts = tuple(
        part
        .strip()
        .lower()

        for part
        in table_name.split(".")

        if part.strip()
    )

    if len(parts) == 1:

        mapping[
            parts[0]
        ] = columns

        return

    if len(parts) == 2:

        project, table = parts

        mapping.setdefault(
            project,
            {},
        )[
            table
        ] = columns

        return

    if len(parts) == 3:

        (
            catalog,
            project,
            table,
        ) = parts

        mapping.setdefault(
            catalog,
            {},
        ).setdefault(
            project,
            {},
        )[
            table
        ] = columns

        return

    raise LineageEvidenceError(
        "Unsupported SQLGlot "
        "table identity depth: "
        f"{table_name!r}."
    )


def _column_ref_sort_key(
    ref: PhysicalColumnRef,
) -> tuple[
    str,
    str,
]:

    return (
        ref.table_full_name,
        ref.column_name,
    )