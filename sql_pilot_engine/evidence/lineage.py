from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlglot import exp, to_column
from sqlglot.errors import SqlglotError
from sqlglot.lineage import Node, to_node
from sqlglot.optimizer import (
    build_scope,
    qualify,
)
from sqlglot.schema import MappingSchema

from sql_pilot_engine.analysis.sql_parser import (
    SQLParser,
)
from sql_pilot_engine.dialects.sqlglot import (
    resolve_sqlglot_dialect,
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


class DerivedLineageStatus(
    str,
    Enum,
):
    """
    SQL Derived Lineage 的完成状态。

    RESOLVED:
        已完整追溯到物理字段。

    NO_PHYSICAL_UPSTREAM:
        当前表达式确实没有物理字段依赖，
        例如常量或静态分区值。

    PARTIAL:
        部分来源已经追到物理字段，
        但仍然存在 unresolved leaf。

    UNRESOLVED:
        没有得到可靠物理字段来源。

    ERROR:
        SQLGlot Lineage 执行失败。
    """

    RESOLVED = "resolved"

    NO_PHYSICAL_UPSTREAM = (
        "no_physical_upstream"
    )

    PARTIAL = "partial"

    UNRESOLVED = "unresolved"

    ERROR = "error"


class LineageDiffKind(
    str,
    Enum,
):
    """
    Declared 与 Derived 血缘之间的事实关系。

    注意：
    这里不是 Review Verdict。
    """

    MATCH = "match"

    DECLARED_ONLY = (
        "declared_only"
    )

    DERIVED_ONLY = (
        "derived_only"
    )

    PATH_MISMATCH = (
        "path_mismatch"
    )

    NOT_COMPARABLE = (
        "not_comparable"
    )


@dataclass(
    frozen=True,
    slots=True,
)
class LineageDiff:
    """
    Declared / Derived 的集合差异。

    declared_only:
        Metadata 登记了，
        但 SQL Derived 中没有。

    derived_only:
        SQL 实际使用了，
        但 Metadata 没登记。
    """

    kind: LineageDiffKind

    declared_only: tuple[
        PhysicalColumnRef,
        ...,
    ] = ()

    derived_only: tuple[
        PhysicalColumnRef,
        ...,
    ] = ()


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnLineageEvidence:
    """
    一个写入目标字段的双源 Lineage Evidence。

    target:
        目标物理字段。

    declared_upstream:
        来自 Metadata 的直接上游字段。

    derived_upstream:
        SQLGlot 从实际 SQL 推导出的
        最终物理叶子字段。

    diff:
        两者之间的事实差异。

    本 DTO 不产生：
        Issue
        Severity
        Fix Suggestion
    """

    target: PhysicalColumnRef

    declared_upstream: tuple[
        PhysicalColumnRef,
        ...,
    ]

    declared_status: (
        str | None
    )

    derived_upstream: tuple[
        PhysicalColumnRef,
        ...,
    ]

    derived_status: (
        DerivedLineageStatus
    )

    diff: LineageDiff

    statement_index: int

    projection_index: (
        int | None
    )

    expression_sql: (
        str | None
    ) = None

    unresolved_sources: tuple[
        str,
        ...,
    ] = ()

    error_message: (
        str | None
    ) = None


@dataclass(
    frozen=True,
    slots=True,
)
class ProgramLineageEvidence:
    """
    一份 SQLProgram 的字段级 Lineage Evidence。
    """

    columns: tuple[
        ColumnLineageEvidence,
        ...,
    ]


class LineageEvidenceError(
    RuntimeError,
):
    """
    正式 Lineage Evidence
    无法满足前置条件时抛出的错误。

    例如：

    - READ_SOURCE Metadata 未解析；
    - WRITE_TARGET Metadata 未解析；
    - INSERT projection 数量与目标字段不一致；
    - SQLGlot qualification 失败。

    这些不能伪装成正常 Lineage Evidence。
    """


@dataclass(
    frozen=True,
    slots=True,
)
class _ProjectionTarget:
    """
    INSERT Target Field
        ↔
    SELECT Projection

    的内部位置映射。

    static partition：

        projection_index = None
    """

    column_name: str

    projection_index: (
        int | None
    )

    static_partition_value: (
        str | None
    ) = None


class LineageEvidenceResolver:
    """
    SQLProgram
        +
    ProgramMetadataEvidence
        ↓
    ProgramLineageEvidence


    --------------------------------------------------------
    Ownership
    --------------------------------------------------------

    Program:
        只描述 SQL 是什么。

    MetadataEvidence:
        解决 SQL identifier
        对应哪张物理表。

    SQLGlot:
        负责 CTE / Scope / UNION /
        aggregation / subquery 等
        字段传播算法。

    LineageEvidenceResolver:
        负责：

        1. Metadata → MappingSchema；
        2. INSERT projection → target field；
        3. SQLGlot Node → PhysicalColumnRef；
        4. Declared / Derived Diff。


    不负责：

        Finding
        Severity
        Fix
        Explain
    """

    def __init__(
        self,
        *,
        parser: (
            SQLParser | None
        ) = None,
    ) -> None:

        self._parser = (
            parser
            or SQLParser()
        )

    def resolve(
        self,
        program: SQLProgram,
        metadata_evidence: (
            ProgramMetadataEvidence
        ),
        *,
        dialect: str = "maxcompute",
    ) -> ProgramLineageEvidence:

        sqlglot_dialect = (
            resolve_sqlglot_dialect(
                dialect
            )
        )

        # ==================================================
        # 1. READ SOURCE Metadata
        #
        # 正式 Lineage 不猜。
        #
        # 任何 READ_SOURCE Metadata
        # 没解析成功，都不能宣称获得
        # authoritative derived lineage。
        # ==================================================

        source_resolutions = (
            self._resolved_read_sources(
                metadata_evidence
            )
        )

        source_schema = (
            self._build_mapping_schema(
                source_resolutions,
                dialect=(
                    sqlglot_dialect
                ),
            )
        )

        # ==================================================
        # 2. Bare Name → Canonical
        #
        # ProgramMetadataResolver 已经完成：
        #
        # loan_detail
        #     ↓
        # project.loan_detail
        #
        # Lineage 不重新解析。
        #
        # 这里只把已经确认的结果同步给
        # SQLGlot AST。
        # ==================================================

        source_replacements = {
            item.requested_table:
                item.canonical_table

            for item
            in source_resolutions

            if (
                item.canonical_table
                is not None

                and (
                    item.requested_table
                    != item.canonical_table
                )
            )
        }

        # ==================================================
        # 3. WRITE TARGET Metadata
        # ==================================================

        target_resolutions = {
            item.requested_table:
                item

            for item
            in metadata_evidence.tables

            if (
                item.role
                is MetadataObjectRole
                .WRITE_TARGET
            )
        }

        evidence: list[
            ColumnLineageEvidence
        ] = []

        # ==================================================
        # 4. Statement-by-Statement
        # ==================================================

        for statement in (
            program.statements
        ):

            if (
                statement.write_target
                is None
            ):
                continue

            requested_target = (
                statement
                .write_target
                .table_name
                .strip()
                .lower()
            )

            target_resolution = (
                target_resolutions.get(
                    requested_target
                )
            )

            target_metadata = (
                self
                ._require_target_metadata(
                    statement=statement,
                    resolution=(
                        target_resolution
                    ),
                )
            )

            # ----------------------------------------------
            # SQLProgram 不保存 SQLGlot AST。
            #
            # Lineage 需要时重新 Parse。
            #
            # AST 仍然只是第三方 Compiler Object，
            # 不进入 Agent3 Domain。
            # ----------------------------------------------

            expression = (
                self._parse_statement(
                    statement,
                    dialect=dialect,
                )
            )

            query = (
                self._extract_query(
                    expression
                )
            )

            if query is None:
                raise LineageEvidenceError(
                    "Write statement does not "
                    "contain a lineage-capable "
                    "query: "
                    f"statement="
                    f"{statement.index}."
                )

            # ----------------------------------------------
            # Bare physical source 已经经过
            # MetadataEvidence 唯一解析后，
            # 才允许替换成 canonical identity。
            # ----------------------------------------------

            if source_replacements:

                query = (
                    exp.replace_tables(
                        query,
                        source_replacements,
                        dialect=(
                            sqlglot_dialect
                        ),
                        copy=True,
                    )
                )

            # ==================================================
            # 5. Qualification
            # ==================================================

            try:

                qualified_query = (
                    qualify.qualify(
                        query.copy(),

                        dialect=(
                            sqlglot_dialect
                        ),

                        schema=(
                            source_schema
                        ),

                        # 正式 Lineage：
                        # Metadata 完整时使用严格校验。
                        validate_qualify_columns=(
                            True
                        ),

                        identify=False,
                    )
                )

            except (
                SqlglotError,
                ValueError,
            ) as exc:

                raise LineageEvidenceError(
                    "SQLGlot qualification "
                    "failed for statement "
                    f"{statement.index}: "
                    f"{exc}"
                ) from exc

            # ==================================================
            # 6. SQLGlot Scope
            # ==================================================

            scope = build_scope(
                qualified_query
            )

            if scope is None:
                raise LineageEvidenceError(
                    "SQLGlot could not build "
                    "lineage scope for "
                    f"statement "
                    f"{statement.index}."
                )

            # ==================================================
            # 7. SELECT projection
            #        ↓
            #    Target Column
            #
            # 位置映射，不依赖 alias。
            # ==================================================

            projection_targets = (
                self
                ._projection_targets(
                    statement=statement,

                    target_metadata=(
                        target_metadata
                    ),

                    projection_count=(
                        len(
                            scope
                            .expression
                            .selects
                        )
                    ),
                )
            )

            by_column = {
                item.column_name:
                    item

                for item
                in projection_targets
            }

            # ==================================================
            # 8. Target Field Lineage
            # ==================================================

            for target_column in (
                sorted(
                    target_metadata
                    .columns
                    .values(),

                    key=lambda item: (
                        item
                        .technical
                        .ordinal_position
                    ),
                )
            ):

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

                projection_target = (
                    by_column[
                        target_column.name
                    ]
                )

                # ==========================================
                # Static Partition
                #
                # PARTITION(dt='202609')
                #
                # dt 不占 SELECT projection，
                # 并且没有物理字段 upstream。
                # ==========================================

                if (
                    projection_target
                    .projection_index
                    is None
                ):

                    derived_upstream: tuple[
                        PhysicalColumnRef,
                        ...,
                    ] = ()

                    derived_status = (
                        DerivedLineageStatus
                        .NO_PHYSICAL_UPSTREAM
                    )

                    unresolved_sources: tuple[
                        str,
                        ...,
                    ] = ()

                    error_message = None

                    expression_sql = (
                        projection_target
                        .static_partition_value
                    )

                else:

                    projection_index = (
                        projection_target
                        .projection_index
                    )

                    projection = (
                        scope
                        .expression
                        .selects[
                            projection_index
                        ]
                    )

                    expression_sql = (
                        projection.sql(
                            dialect=(
                                sqlglot_dialect
                            ),
                            pretty=False,
                        )
                    )

                    try:

                        root = to_node(
                            projection_index,

                            scope=scope,

                            dialect=(
                                sqlglot_dialect
                            ),

                            trim_selects=True,
                        )

                        (
                            derived_upstream,
                            unresolved_sources,
                            derived_status,
                        ) = (
                            self
                            ._derived_leaf_evidence(
                                root,
                                dialect=(
                                    sqlglot_dialect
                                ),
                            )
                        )

                        error_message = None

                    except (
                        SqlglotError,
                        ValueError,
                    ) as exc:

                        derived_upstream = ()

                        unresolved_sources = ()

                        derived_status = (
                            DerivedLineageStatus
                            .ERROR
                        )

                        error_message = str(
                            exc
                        )

                # ==========================================
                # Declared Lineage
                # ==========================================

                declared_upstream = tuple(
                    sorted(
                        target_column
                        .technical
                        .declared_upstream_columns,

                        key=(
                            _column_ref_sort_key
                        ),
                    )
                )

                # ==========================================
                # Declared vs Derived
                # ==========================================

                diff = (
                    _build_lineage_diff(
                        declared=(
                            declared_upstream
                        ),

                        derived=(
                            derived_upstream
                        ),

                        derived_status=(
                            derived_status
                        ),
                    )
                )

                evidence.append(
                    ColumnLineageEvidence(
                        target=(
                            target_ref
                        ),

                        declared_upstream=(
                            declared_upstream
                        ),

                        declared_status=(
                            target_column
                            .management
                            .lineage_confirmation_status
                        ),

                        derived_upstream=(
                            derived_upstream
                        ),

                        derived_status=(
                            derived_status
                        ),

                        diff=diff,

                        statement_index=(
                            statement.index
                        ),

                        projection_index=(
                            projection_target
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
                evidence
            )
        )

    # ======================================================
    # Metadata Preconditions
    # ======================================================

    @staticmethod
    def _resolved_read_sources(
        metadata_evidence: (
            ProgramMetadataEvidence
        ),
    ) -> tuple[
        TableMetadataResolution,
        ...,
    ]:

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

                or (
                    item.canonical_table
                    is None
                )
            )
        )

        if blocked:

            details = ", ".join(
                (
                    f"{item.requested_table}"
                    f"[{item.status.value}]"
                )

                for item
                in blocked
            )

            raise LineageEvidenceError(
                "Lineage requires resolved "
                "read-source Metadata: "
                + details
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

                if resolution
                is not None

                else "missing_resolution"
            )

            assert (
                statement.write_target
                is not None
            )

            raise LineageEvidenceError(
                "Lineage requires resolved "
                "write-target Metadata: "
                f"statement="
                f"{statement.index}, "
                f"target="
                f"{statement.write_target.table_name!r}, "
                f"status={status}."
            )

        return resolution.metadata

    # ======================================================
    # SQL → Query
    # ======================================================

    def _parse_statement(
        self,
        statement: SQLStatement,
        *,
        dialect: str,
    ) -> exp.Expression:

        result = self._parser.parse(
            statement.normalized_sql,
            dialect=dialect,
        )

        if (
            not result.success
            or len(result.statements) != 1
        ):

            raise LineageEvidenceError(
                "Lineage could not reparse "
                "SQLStatement "
                f"{statement.index}: "
                f"{result.error_message}"
            )

        return result.statements[0]

    @staticmethod
    def _extract_query(
        expression: exp.Expression,
    ) -> exp.Query | None:
        """
        SELECT：
            自身就是 Query。

        INSERT：
            获取内部 SELECT / UNION Query。

        对：

            WITH ...
            INSERT ...
            SELECT ...

        如果 WITH 挂在 INSERT 上，
        需要复制回内部 Query，
        保证完整 CTE DAG。
        """

        if isinstance(
            expression,
            exp.Query,
        ):
            return expression.copy()

        if not isinstance(
            expression,
            exp.Insert,
        ):
            return None

        query = (
            expression.args.get(
                "expression"
            )
        )

        if not isinstance(
            query,
            exp.Query,
        ):
            return None

        query = query.copy()

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
            statement_with
            is not None

            and query_with
            is None
        ):

            query.set(
                "with_",
                statement_with.copy(),
            )

        return query

    # ======================================================
    # Metadata → SQLGlot MappingSchema
    # ======================================================

    @staticmethod
    def _build_mapping_schema(
        resolutions: tuple[
            TableMetadataResolution,
            ...,
        ],
        *,
        dialect: str,
    ) -> MappingSchema:

        nested: dict[
            str,
            object,
        ] = {}

        for resolution in (
            resolutions
        ):

            assert (
                resolution.metadata
                is not None
            )

            assert (
                resolution.canonical_table
                is not None
            )

            table = resolution.metadata

            parts = (
                table.full_name
                .split(".")
            )

            columns = {
                column.name: (
                    column
                    .technical
                    .data_type
                    or None
                )

                for column
                in table.columns.values()
            }

            # ----------------------------------------------
            # table
            # ----------------------------------------------

            if len(parts) == 1:

                nested[
                    parts[0]
                ] = columns

                continue

            # ----------------------------------------------
            # project.table
            # ----------------------------------------------

            if len(parts) == 2:

                (
                    project,
                    table_name,
                ) = parts

                project_mapping = (
                    nested.setdefault(
                        project,
                        {},
                    )
                )

                if not isinstance(
                    project_mapping,
                    dict,
                ):
                    raise LineageEvidenceError(
                        "Mixed Metadata "
                        "identity depth is "
                        "not supported."
                    )

                project_mapping[
                    table_name
                ] = columns

                continue

            # ----------------------------------------------
            # catalog.project.table
            # ----------------------------------------------

            if len(parts) == 3:

                (
                    catalog,
                    project,
                    table_name,
                ) = parts

                catalog_mapping = (
                    nested.setdefault(
                        catalog,
                        {},
                    )
                )

                if not isinstance(
                    catalog_mapping,
                    dict,
                ):
                    raise LineageEvidenceError(
                        "Mixed Metadata "
                        "identity depth is "
                        "not supported."
                    )

                project_mapping = (
                    catalog_mapping
                    .setdefault(
                        project,
                        {},
                    )
                )

                if not isinstance(
                    project_mapping,
                    dict,
                ):
                    raise LineageEvidenceError(
                        "Mixed Metadata "
                        "identity depth is "
                        "not supported."
                    )

                project_mapping[
                    table_name
                ] = columns

                continue

            raise LineageEvidenceError(
                "SQLGlot MappingSchema "
                "only supports physical "
                "identity depth 1-3: "
                f"{table.full_name!r}."
            )

        return MappingSchema(
            nested,
            dialect=dialect,
        )

    # ======================================================
    # INSERT Projection → Target Column
    # ======================================================

    @staticmethod
    def _projection_targets(
        *,
        statement: SQLStatement,
        target_metadata: TableMetadata,
        projection_count: int,
    ) -> tuple[
        _ProjectionTarget,
        ...,
    ]:

        target = (
            statement.write_target
        )

        if target is None:
            raise LineageEvidenceError(
                "Projection target mapping "
                "requires WriteTarget."
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
            item.name
            .strip()
            .lower():
                item

            for item
            in target.partition_spec
        }

        unknown_partition_names = (
            set(
                partition_bindings
            )
            - partition_set
        )

        if unknown_partition_names:
            raise LineageEvidenceError(
                "INSERT partition fields "
                "are absent from target "
                "Metadata: "
                f"{sorted(unknown_partition_names)!r}."
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

        ordered_columns = tuple(
            sorted(
                target_metadata
                .columns
                .values(),

                key=lambda item: (
                    item
                    .technical
                    .ordinal_position
                ),
            )
        )

        # ----------------------------------------------
        # 普通字段
        # ----------------------------------------------

        regular_names = tuple(
            column.name

            for column
            in ordered_columns

            if (
                column.name
                not in partition_set
            )
        )

        # ----------------------------------------------
        # 未被 static PARTITION 固定的分区字段
        # 必须来自 SELECT。
        # ----------------------------------------------

        dynamic_partition_names = (
            tuple(
                name

                for name
                in partition_fields

                if (
                    name
                    not in
                    static_partition_names
                )
            )
        )

        projection_names = (
            regular_names
            + dynamic_partition_names
        )

        if (
            len(projection_names)
            != projection_count
        ):

            raise LineageEvidenceError(
                "INSERT projection count "
                "does not match target "
                "Metadata: "
                f"statement="
                f"{statement.index}, "
                f"target="
                f"{target_metadata.full_name!r}, "
                f"expected="
                f"{len(projection_names)}, "
                f"actual="
                f"{projection_count}."
            )

        by_name: dict[
            str,
            _ProjectionTarget,
        ] = {
            name: (
                _ProjectionTarget(
                    column_name=name,
                    projection_index=(
                        index
                    ),
                )
            )

            for (
                index,
                name,
            )
            in enumerate(
                projection_names
            )
        }

        # ----------------------------------------------
        # Static Partition
        # ----------------------------------------------

        for name in (
            static_partition_names
        ):

            binding = (
                partition_bindings[
                    name
                ]
            )

            by_name[
                name
            ] = (
                _ProjectionTarget(
                    column_name=name,

                    projection_index=None,

                    static_partition_value=(
                        binding.value
                    ),
                )
            )

        missing = {
            column.name

            for column
            in ordered_columns
        } - set(by_name)

        if missing:
            raise LineageEvidenceError(
                "Target Metadata columns "
                "could not be mapped to "
                "INSERT output: "
                f"{sorted(missing)!r}."
            )

        return tuple(
            by_name[
                column.name
            ]

            for column
            in ordered_columns
        )

    # ======================================================
    # SQLGlot Node → PhysicalColumnRef
    # ======================================================

    @staticmethod
    def _derived_leaf_evidence(
        root: Node,
        *,
        dialect: str,
    ) -> tuple[
        tuple[
            PhysicalColumnRef,
            ...,
        ],
        tuple[
            str,
            ...,
        ],
        DerivedLineageStatus,
    ]:

        physical: set[
            PhysicalColumnRef
        ] = set()

        unresolved: set[
            str
        ] = set()

        for node in root.walk():

            # 只看最终叶节点。
            if node.downstream:
                continue

            # ------------------------------------------
            # Physical Table Leaf
            # ------------------------------------------

            if isinstance(
                node.expression,
                exp.Table,
            ):

                # SQLGlot Node.name 保存：
                #
                # table.column
                #
                # 继续交给 SQLGlot 自己解析，
                # 不手工 split identifier。
                column = to_column(
                    node.name,
                    dialect=dialect,
                )

                physical.add(
                    PhysicalColumnRef(
                        table_full_name=(
                            exp.table_name(
                                node.expression,
                                dialect=dialect,
                            )
                        ),

                        column_name=(
                            column.name
                        ),
                    )
                )

                continue

            # ------------------------------------------
            # Unknown Leaf
            # ------------------------------------------

            if isinstance(
                node.expression,
                exp.Placeholder,
            ):

                unresolved.add(
                    node.name
                )

        physical_result = tuple(
            sorted(
                physical,
                key=(
                    _column_ref_sort_key
                ),
            )
        )

        unresolved_result = tuple(
            sorted(
                unresolved
            )
        )

        if (
            physical_result
            and unresolved_result
        ):
            status = (
                DerivedLineageStatus
                .PARTIAL
            )

        elif unresolved_result:
            status = (
                DerivedLineageStatus
                .UNRESOLVED
            )

        elif physical_result:
            status = (
                DerivedLineageStatus
                .RESOLVED
            )

        else:
            status = (
                DerivedLineageStatus
                .NO_PHYSICAL_UPSTREAM
            )

        return (
            physical_result,
            unresolved_result,
            status,
        )


def _build_lineage_diff(
    *,
    declared: tuple[
        PhysicalColumnRef,
        ...,
    ],

    derived: tuple[
        PhysicalColumnRef,
        ...,
    ],

    derived_status: (
        DerivedLineageStatus
    ),
) -> LineageDiff:
    """
    比较 Declared / Derived。

    只有 Derived 已经可靠完成，
    才允许进行差异分类。

    PARTIAL / UNRESOLVED / ERROR
    一律 NOT_COMPARABLE。
    """

    if derived_status in {
        DerivedLineageStatus.PARTIAL,
        DerivedLineageStatus.UNRESOLVED,
        DerivedLineageStatus.ERROR,
    }:

        return LineageDiff(
            kind=(
                LineageDiffKind
                .NOT_COMPARABLE
            )
        )

    declared_set = set(
        declared
    )

    derived_set = set(
        derived
    )

    declared_only = tuple(
        sorted(
            (
                declared_set
                - derived_set
            ),

            key=(
                _column_ref_sort_key
            ),
        )
    )

    derived_only = tuple(
        sorted(
            (
                derived_set
                - declared_set
            ),

            key=(
                _column_ref_sort_key
            ),
        )
    )

    # --------------------------------------------------
    # 完全一致
    # --------------------------------------------------

    if (
        not declared_only
        and not derived_only
    ):

        kind = (
            LineageDiffKind.MATCH
        )

    # --------------------------------------------------
    # Metadata 有，SQL 无
    # --------------------------------------------------

    elif (
        declared_set
        and not derived_set
    ):

        kind = (
            LineageDiffKind
            .DECLARED_ONLY
        )

    # --------------------------------------------------
    # SQL 有，Metadata 无
    # --------------------------------------------------

    elif (
        derived_set
        and not declared_set
    ):

        kind = (
            LineageDiffKind
            .DERIVED_ONLY
        )

    # --------------------------------------------------
    # 双方都有，但路径不一致
    # --------------------------------------------------

    else:

        kind = (
            LineageDiffKind
            .PATH_MISMATCH
        )

    return LineageDiff(
        kind=kind,

        declared_only=(
            declared_only
        ),

        derived_only=(
            derived_only
        ),
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