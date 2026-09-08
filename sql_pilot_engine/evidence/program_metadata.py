from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sql_pilot_engine.analysis.facts import (
    ColumnReference,
)
from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    MetadataLookupStatus,
    TableLookupResult,
    TableMetadata,
)
from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)
from sql_pilot_engine.metadata.catalog import (
    MetadataCatalog,
)
from sql_pilot_engine.program.enums import (
    SourceBindingKind,
)
from sql_pilot_engine.program.models import (
    ProgramScopeAnalysis,
    ScopeSourceBinding,
    SQLProgram,
)


class MetadataObjectRole(
    str,
    Enum,
):
    """
    一个物理表在 SQLProgram 中承担的角色。

    READ_SOURCE：
        SQL 从该表读取数据。

    WRITE_TARGET：
        SQL 向该表写入数据。

    同一张物理表理论上可能同时承担两个角色，
    因此 Evidence 中不做角色合并。
    """

    READ_SOURCE = "read_source"

    WRITE_TARGET = "write_target"


class ColumnResolutionStatus(
    str,
    Enum,
):
    """
    一个字段引用相对于权威 Metadata 的解析状态。

    RESOLVED：
        已确定具体物理表，
        且字段真实存在。

    ABSENT：
        已确定具体物理表，
        表真实存在，
        但字段确认不存在。

    SOURCE_ABSENT：
        已确定引用的物理表，
        但该表在权威 Metadata 中不存在。

    SOURCE_ERROR：
        MetadataProvider 查询失败。

    UNRESOLVED_SOURCE：
        SQL 结构自身不足以把字段唯一绑定到一个 Source。
        例如多表 JOIN 中的无 qualifier 字段。

        这不是 Metadata 不完整。

    NON_PHYSICAL_SOURCE：
        字段当前绑定到 CTE / derived Scope，
        因此不能直接向 Physical Metadata 查询。
        后续由 Column Lineage 向上追溯。

    SELECT_ALIAS：
        当前引用是 SELECT 输出 alias，
        不是物理字段引用。
    """

    RESOLVED = "resolved"

    ABSENT = "absent"

    SOURCE_ABSENT = "source_absent"

    SOURCE_ERROR = "source_error"

    UNRESOLVED_SOURCE = (
        "unresolved_source"
    )

    NON_PHYSICAL_SOURCE = (
        "non_physical_source"
    )

    SELECT_ALIAS = "select_alias"


class TableResolutionStatus(
    str,
    Enum,
):
    RESOLVED = "resolved"

    ABSENT = "absent"

    AMBIGUOUS = "ambiguous"

    ERROR = "error"
    

@dataclass(
    frozen=True,
    slots=True,
)
class TableMetadataResolution:
    """
    SQL 中一个 table reference
    相对于权威 Metadata 的解析结果。

    requested_table:
        SQL 原始引用。

    canonical_table:
        唯一解析后的完整物理表名。

    candidates:
        AMBIGUOUS 时保存全部候选。
    """

    role: MetadataObjectRole

    requested_table: str

    status: TableResolutionStatus

    canonical_table: str | None = None

    candidates: tuple[
        str,
        ...,
    ] = ()

    metadata: TableMetadata | None = None

    error_message: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnMetadataResolution:
    """
    SQLProgram 中一个 ColumnReference 的 Metadata Evidence。
    """

    scope_id: str

    column: ColumnReference

    status: ColumnResolutionStatus

    source_alias: str | None = None

    physical_table: str | None = None

    source_scope_id: str | None = None

    metadata: ColumnMetadata | None = None

    error_message: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class ProgramMetadataEvidence:
    """
    SQLProgram 对权威 Physical Metadata 的解析证据。

    本 DTO 只表达事实。

    它不生成：
    - Issue；
    - Severity；
    - BLOCK / WARNING；
    - Fix suggestion。

    是否构成问题，由后续 Review /
    Generate Validation 决定。
    """

    tables: tuple[
        TableMetadataResolution,
        ...,
    ]

    columns: tuple[
        ColumnMetadataResolution,
        ...,
    ]


class ProgramMetadataResolver:
    """
    SQLProgram + MetadataProvider
        → ProgramMetadataEvidence

    【架构位置】

        SQLProgram
            ↓
    ProgramMetadataResolver
            ↓
    ProgramMetadataEvidence

    该 Resolver：

    - 不修改 SQLProgram；
    - 不依赖 LLM；
    - 不做模糊搜索；
    - 不做 Column Lineage；
    - 不产生 Review verdict。
    """

    def __init__(
        self,
        provider: MetadataProvider,
        catalog: MetadataCatalog,
    ) -> None:
        self._provider = provider
        self._catalog = catalog

    def resolve(
        self,
        program: SQLProgram,
    ) -> ProgramMetadataEvidence:

        cache: dict[
            str,
            TableLookupResult,
        ] = {}

        tables = (
            self._resolve_tables(
                program=program,
                cache=cache,
            )
        )

        columns = (
            self._resolve_columns(
                program=program,
                cache=cache,
            )
        )

        return ProgramMetadataEvidence(
            tables=tables,
            columns=columns,
        )

    def _resolve_tables(
        self,
        *,
        program: SQLProgram,
        cache: dict[
            str,
            TableLookupResult,
        ],
    ) -> tuple[
        TableMetadataResolution,
        ...,
    ]:

        requests: list[
            tuple[
                MetadataObjectRole,
                str,
            ]
        ] = []

        seen: set[
            tuple[
                MetadataObjectRole,
                str,
            ]
        ] = set()

        # --------------------------------------------------
        # Physical READ sources
        # --------------------------------------------------

        for scope in (
            program.scope_analyses
        ):
            for binding in (
                scope.source_bindings
            ):
                if (
                    binding.kind
                    is not (
                        SourceBindingKind
                        .PHYSICAL_TABLE
                    )
                ):
                    continue

                assert (
                    binding.physical_table
                    is not None
                )

                key = (
                    MetadataObjectRole
                    .READ_SOURCE,
                    binding.physical_table,
                )

                if key in seen:
                    continue

                seen.add(key)
                requests.append(key)

        # --------------------------------------------------
        # WRITE targets
        # --------------------------------------------------

        for statement in (
            program.statements
        ):
            target = (
                statement.write_target
            )

            if target is None:
                continue

            table_name = (
                target.table_name
                .strip()
                .lower()
            )

            key = (
                MetadataObjectRole
                .WRITE_TARGET,
                table_name,
            )

            if key in seen:
                continue

            seen.add(key)
            requests.append(key)

        resolutions: list[
            TableMetadataResolution
        ] = []

        for (
            role,
            table_name,
        ) in requests:

            result = self._lookup(
                table_name=table_name,
                cache=cache,
            )

            resolutions.append(
                TableMetadataResolution(
                    role=role,
                    requested_table=(
                        table_name
                    ),
                    status=(
                        result.status
                    ),
                    metadata=(
                        result.table
                    ),
                    error_message=(
                        result.error_message
                    ),
                )
            )

        return tuple(
            resolutions
        )

    def _resolve_table_identifier(
        self,
        *,
        role: MetadataObjectRole,
        requested_table: str,
        lookup_cache: dict[
            str,
            TableLookupResult,
        ],
    ) -> TableMetadataResolution:

        normalized = (
            requested_table
            .strip()
            .lower()
        )

        # --------------------------------------------------
        # 已经带 namespace / project
        #
        # 必须 exact lookup。
        # --------------------------------------------------

        if "." in normalized:

            result = self._lookup(
                table_name=normalized,
                cache=lookup_cache,
            )

            if (
                result.status
                is MetadataLookupStatus.ERROR
            ):
                return (
                    TableMetadataResolution(
                        role=role,
                        requested_table=normalized,
                        status=(
                            TableResolutionStatus.ERROR
                        ),
                        error_message=(
                            result.error_message
                        ),
                    )
                )

            if (
                result.status
                is MetadataLookupStatus.NOT_FOUND
            ):
                return (
                    TableMetadataResolution(
                        role=role,
                        requested_table=normalized,
                        status=(
                            TableResolutionStatus.ABSENT
                        ),
                    )
                )

            if result.table is None:
                raise RuntimeError(
                    "MetadataProvider returned "
                    "FOUND without TableMetadata."
                )

            return (
                TableMetadataResolution(
                    role=role,
                    requested_table=normalized,
                    status=(
                        TableResolutionStatus.RESOLVED
                    ),
                    canonical_table=(
                        result.table.full_name
                    ),
                    metadata=(
                        result.table
                    ),
                )
            )

        # --------------------------------------------------
        # 没带空间名：
        # 查全部 canonical candidates。
        # --------------------------------------------------

        candidates = (
            self._catalog
            .find_table_identifiers(
                normalized
            )
        )

        candidate_names = tuple(
            candidate.full_name
            for candidate
            in candidates
        )

        if not candidate_names:

            return (
                TableMetadataResolution(
                    role=role,
                    requested_table=normalized,
                    status=(
                        TableResolutionStatus.ABSENT
                    ),
                )
            )

        if len(candidate_names) > 1:

            return (
                TableMetadataResolution(
                    role=role,
                    requested_table=normalized,
                    status=(
                        TableResolutionStatus
                        .AMBIGUOUS
                    ),
                    candidates=(
                        candidate_names
                    ),
                )
            )

        canonical = (
            candidate_names[0]
        )

        result = self._lookup(
            table_name=canonical,
            cache=lookup_cache,
        )

        # Catalog 与 Provider 使用同一权威事实库，
        # 这里理论上必须 FOUND。
        if (
            result.status
            is not MetadataLookupStatus.FOUND
            or result.table is None
        ):
            return (
                TableMetadataResolution(
                    role=role,
                    requested_table=normalized,
                    status=(
                        TableResolutionStatus.ERROR
                    ),
                    canonical_table=(
                        canonical
                    ),
                    error_message=(
                        "MetadataCatalog resolved "
                        f"{normalized!r} to "
                        f"{canonical!r}, but "
                        "MetadataProvider could not "
                        "load the canonical table."
                    ),
                )
            )

        return (
            TableMetadataResolution(
                role=role,
                requested_table=normalized,
                status=(
                    TableResolutionStatus.RESOLVED
                ),
                canonical_table=(
                    canonical
                ),
                metadata=(
                    result.table
                ),
            )
        )


    def _resolve_unqualified_column(
        self,
        *,
        scope: ProgramScopeAnalysis,
        column: ColumnReference,
        lookup_cache: dict[
            str,
            TableLookupResult,
        ],
    ) -> ColumnMetadataResolution:

        resolved_candidates: list[
            tuple[
                ScopeSourceBinding,
                TableMetadata,
                ColumnMetadata,
            ]
        ] = []

        ambiguous_sources: list[str] = []

        has_non_physical_source = False

        has_unresolved_source = False

        for binding in (
            scope.source_bindings
        ):

            # ----------------------------------------------
            # CTE / subquery
            #
            # Metadata 无法直接证明内部字段来源，
            # 留给 4.5 Lineage。
            # ----------------------------------------------

            if (
                binding.kind
                is SourceBindingKind.SCOPE
            ):
                has_non_physical_source = True
                continue

            if (
                binding.kind
                is SourceBindingKind.UNRESOLVED
            ):
                has_unresolved_source = True
                continue

            assert (
                binding.physical_table
                is not None
            )

            table_resolution = (
                self._resolve_table_identifier(
                    role=(
                        MetadataObjectRole
                        .READ_SOURCE
                    ),
                    requested_table=(
                        binding.physical_table
                    ),
                    lookup_cache=(
                        lookup_cache
                    ),
                )
            )

            if (
                table_resolution.status
                is TableResolutionStatus.AMBIGUOUS
            ):
                ambiguous_sources.append(
                    binding.alias
                )

                continue

            if (
                table_resolution.status
                is TableResolutionStatus.ERROR
            ):
                return (
                    ColumnMetadataResolution(
                        scope_id=scope.scope_id,
                        column=column,
                        status=(
                            ColumnResolutionStatus
                            .SOURCE_ERROR
                        ),
                        source_alias=(
                            binding.alias
                        ),
                        error_message=(
                            table_resolution
                            .error_message
                        ),
                    )
                )

            if (
                table_resolution.status
                is TableResolutionStatus.ABSENT
            ):
                return (
                    ColumnMetadataResolution(
                        scope_id=scope.scope_id,
                        column=column,
                        status=(
                            ColumnResolutionStatus
                            .SOURCE_ABSENT
                        ),
                        source_alias=(
                            binding.alias
                        ),
                    )
                )

            table = (
                table_resolution.metadata
            )

            assert table is not None

            column_metadata = (
                table.get_column(
                    column.name
                )
            )

            if column_metadata is None:
                continue

            resolved_candidates.append(
                (
                    binding,
                    table,
                    column_metadata,
                )
            )

        # --------------------------------------------------
        # 表本身存在命名歧义。
        # --------------------------------------------------

        if ambiguous_sources:

            return (
                ColumnMetadataResolution(
                    scope_id=scope.scope_id,
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .SOURCE_AMBIGUOUS
                    ),
                    error_message=(
                        "Ambiguous source table "
                        "identifiers: "
                        + ", ".join(
                            ambiguous_sources
                        )
                    ),
                )
            )

        # --------------------------------------------------
        # 两张以上物理表都拥有此字段。
        # --------------------------------------------------

        if (
            len(resolved_candidates)
            > 1
        ):

            candidate_tables = tuple(
                table.full_name
                for (
                    _,
                    table,
                    _,
                )
                in resolved_candidates
            )

            return (
                ColumnMetadataResolution(
                    scope_id=scope.scope_id,
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .AMBIGUOUS
                    ),
                    candidate_tables=(
                        candidate_tables
                    ),
                )
            )

        # --------------------------------------------------
        # 唯一物理表拥有该字段。
        # --------------------------------------------------

        if (
            len(resolved_candidates)
            == 1
        ):
            (
                binding,
                table,
                column_metadata,
            ) = resolved_candidates[0]

            # 如果当前同时存在 CTE / unresolved source，
            # Metadata 单独不能证明 CTE 中没有同名字段。
            #
            # 4.5 使用 SQLGlot qualify + lineage
            # 后再完成最终消歧。
            if (
                has_non_physical_source
                or has_unresolved_source
            ):
                return (
                    ColumnMetadataResolution(
                        scope_id=scope.scope_id,
                        column=column,
                        status=(
                            ColumnResolutionStatus
                            .UNRESOLVED_SOURCE
                        ),
                        physical_table=(
                            table.full_name
                        ),
                        error_message=(
                            "A physical metadata "
                            "candidate exists, but "
                            "the scope also contains "
                            "non-physical or unresolved "
                            "sources."
                        ),
                    )
                )

            return (
                ColumnMetadataResolution(
                    scope_id=scope.scope_id,
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .RESOLVED
                    ),
                    source_alias=(
                        binding.alias
                    ),
                    physical_table=(
                        table.full_name
                    ),
                    metadata=(
                        column_metadata
                    ),
                )
            )

        # --------------------------------------------------
        # 没有物理表拥有字段。
        # --------------------------------------------------

        if (
            has_non_physical_source
            or has_unresolved_source
        ):
            return (
                ColumnMetadataResolution(
                    scope_id=scope.scope_id,
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .UNRESOLVED_SOURCE
                    ),
                )
            )

        return (
            ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=(
                    ColumnResolutionStatus
                    .ABSENT
                ),
            )
        )

    def _resolve_columns(
        self,
        *,
        program: SQLProgram,
        cache: dict[
            str,
            TableLookupResult,
        ],
    ) -> tuple[
        ColumnMetadataResolution,
        ...,
    ]:

        resolutions: list[
            ColumnMetadataResolution
        ] = []

        for scope in (
            program.scope_analyses
        ):

            for column in (
                scope
                .facts
                .column_references
            ):
                resolutions.append(
                    self._resolve_column(
                        scope=scope,
                        column=column,
                        cache=cache,
                    )
                )

        return tuple(
            resolutions
        )

    def _resolve_column(
        self,
        *,
        scope: ProgramScopeAnalysis,
        column: ColumnReference,
        cache: dict[
            str,
            TableLookupResult,
        ],
    ) -> ColumnMetadataResolution:

        # --------------------------------------------------
        # SELECT alias 不是物理字段
        #
        # SQLFacts 本身已经保存 select_aliases。
        # 例如：
        #
        # SUM(amount) AS total_amount
        # ORDER BY total_amount
        #
        # total_amount 不应查询 Metadata。
        # --------------------------------------------------

        if (
            column.qualifier is None
        ):
            return (
                self._resolve_unqualified_column(
                    scope=scope,
                    column=column,
                    lookup_cache=cache,
                )
            )

        binding = (
            self._resolve_binding(
                scope=scope,
                column=column,
            )
        )

        if binding is None:
            return (
                ColumnMetadataResolution(
                    scope_id=(
                        scope.scope_id
                    ),
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .UNRESOLVED_SOURCE
                    ),
                )
            )

        # --------------------------------------------------
        # ScopeSourceBinding 本身未解析
        # --------------------------------------------------

        if (
            binding.kind
            is SourceBindingKind.UNRESOLVED
        ):
            return (
                ColumnMetadataResolution(
                    scope_id=(
                        scope.scope_id
                    ),
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .UNRESOLVED_SOURCE
                    ),
                    source_alias=(
                        binding.alias
                    ),
                    error_message=(
                        binding
                        .unresolved_reason
                    ),
                )
            )

        # --------------------------------------------------
        # CTE / derived scope
        #
        # 不是 Metadata 不完整，
        # 而是当前引用不是物理 Source。
        # --------------------------------------------------

        if (
            binding.kind
            is SourceBindingKind.SCOPE
        ):
            return (
                ColumnMetadataResolution(
                    scope_id=(
                        scope.scope_id
                    ),
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .NON_PHYSICAL_SOURCE
                    ),
                    source_alias=(
                        binding.alias
                    ),
                    source_scope_id=(
                        binding
                        .source_scope_id
                    ),
                )
            )

        assert (
            binding.kind
            is (
                SourceBindingKind
                .PHYSICAL_TABLE
            )
        )

        assert (
            binding.physical_table
            is not None
        )

        table_name = (
            binding.physical_table
        )

        result = self._lookup(
            table_name=table_name,
            cache=cache,
        )

        if (
            result.status
            is MetadataLookupStatus.NOT_FOUND
        ):
            return (
                ColumnMetadataResolution(
                    scope_id=(
                        scope.scope_id
                    ),
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .SOURCE_ABSENT
                    ),
                    source_alias=(
                        binding.alias
                    ),
                    physical_table=(
                        table_name
                    ),
                )
            )

        if (
            result.status
            is MetadataLookupStatus.ERROR
        ):
            return (
                ColumnMetadataResolution(
                    scope_id=(
                        scope.scope_id
                    ),
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .SOURCE_ERROR
                    ),
                    source_alias=(
                        binding.alias
                    ),
                    physical_table=(
                        table_name
                    ),
                    error_message=(
                        result.error_message
                    ),
                )
            )

        table = result.table

        if table is None:
            raise RuntimeError(
                "MetadataProvider returned "
                "FOUND without TableMetadata."
            )

        column_metadata = (
            table.get_column(
                column.name
            )
        )

        if column_metadata is None:
            return (
                ColumnMetadataResolution(
                    scope_id=(
                        scope.scope_id
                    ),
                    column=column,
                    status=(
                        ColumnResolutionStatus
                        .ABSENT
                    ),
                    source_alias=(
                        binding.alias
                    ),
                    physical_table=(
                        table_name
                    ),
                )
            )

        return (
            ColumnMetadataResolution(
                scope_id=(
                    scope.scope_id
                ),
                column=column,
                status=(
                    ColumnResolutionStatus
                    .RESOLVED
                ),
                source_alias=(
                    binding.alias
                ),
                physical_table=(
                    table_name
                ),
                metadata=(
                    column_metadata
                ),
            )
        )

    @staticmethod
    def _resolve_binding(
        *,
        scope: ProgramScopeAnalysis,
        column: ColumnReference,
    ) -> ScopeSourceBinding | None:
        """
        ColumnReference → ScopeSourceBinding。

        规则刻意保守：

        1. 有 qualifier：
           必须 exact alias match。

        2. 无 qualifier：
           当前 Scope 恰好只有一个 Source，
           才允许自动绑定。

        3. 多 Source：
           不猜。
        """

        if column.qualifier:

            qualifier = (
                column.qualifier
                .strip()
                .lower()
            )

            for binding in (
                scope.source_bindings
            ):
                if (
                    binding.alias
                    == qualifier
                ):
                    return binding

            return None

        if (
            len(
                scope.source_bindings
            )
            != 1
        ):
            return None

        return (
            scope.source_bindings[0]
        )

    def _lookup(
        self,
        *,
        table_name: str,
        cache: dict[
            str,
            TableLookupResult,
        ],
    ) -> TableLookupResult:

        normalized = (
            table_name
            .strip()
            .lower()
        )

        result = cache.get(
            normalized
        )

        if result is not None:
            return result

        result = (
            self._provider
            .get_table(
                normalized
            )
        )

        cache[
            normalized
        ] = result

        return result