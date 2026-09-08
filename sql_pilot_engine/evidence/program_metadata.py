from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sql_pilot_engine.analysis.facts import ColumnReference
from sql_pilot_engine.metadata.catalog import MetadataCatalog
from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    MetadataLookupStatus,
    TableLookupResult,
    TableMetadata,
)
from sql_pilot_engine.metadata.provider import MetadataProvider
from sql_pilot_engine.program.enums import SourceBindingKind
from sql_pilot_engine.program.models import (
    ProgramScopeAnalysis,
    ScopeSourceBinding,
    SQLProgram,
)


class MetadataObjectRole(str, Enum):
    """物理表在 SQLProgram 中承担的角色。"""

    READ_SOURCE = "read_source"
    WRITE_TARGET = "write_target"


class TableResolutionStatus(str, Enum):
    """SQL table identifier 相对于权威 Metadata 的解析状态。"""

    RESOLVED = "resolved"
    ABSENT = "absent"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


class ColumnResolutionStatus(str, Enum):
    """SQL column reference 相对于权威 Metadata 的解析状态。"""

    RESOLVED = "resolved"
    ABSENT = "absent"
    AMBIGUOUS = "ambiguous"

    SOURCE_ABSENT = "source_absent"
    SOURCE_AMBIGUOUS = "source_ambiguous"
    SOURCE_ERROR = "source_error"

    UNRESOLVED_SOURCE = "unresolved_source"
    NON_PHYSICAL_SOURCE = "non_physical_source"
    SELECT_ALIAS = "select_alias"


@dataclass(frozen=True, slots=True)
class TableMetadataResolution:
    """一个 SQL table reference 的 canonical Metadata 解析结果。"""

    role: MetadataObjectRole
    requested_table: str
    status: TableResolutionStatus

    canonical_table: str | None = None
    candidates: tuple[str, ...] = ()
    metadata: TableMetadata | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ColumnMetadataResolution:
    """一个 SQL ColumnReference 的 Metadata 解析证据。"""

    scope_id: str
    column: ColumnReference
    status: ColumnResolutionStatus

    source_alias: str | None = None
    physical_table: str | None = None
    source_scope_id: str | None = None
    candidate_tables: tuple[str, ...] = ()
    metadata: ColumnMetadata | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ProgramMetadataEvidence:
    """
    SQLProgram 对权威 Physical Metadata 的确定性解析证据。

    这里只表达事实，不产生 Issue / Severity / Fix suggestion。
    """

    tables: tuple[TableMetadataResolution, ...]
    columns: tuple[ColumnMetadataResolution, ...]


class ProgramMetadataResolver:
    """
    SQLProgram + authoritative Metadata -> ProgramMetadataEvidence。

    设计原则：
    - Program 不回写；
    - Repository 不猜；
    - Resolver 明确执行 0 / 1 / N 候选判定；
    - 不依赖 LLM；
    - 不做 Column Lineage；
    - 不产生 Review verdict。
    """

    def __init__(
        self,
        *,
        provider: MetadataProvider,
        catalog: MetadataCatalog,
    ) -> None:
        self._provider = provider
        self._catalog = catalog

    def resolve(self, program: SQLProgram) -> ProgramMetadataEvidence:
        cache: dict[str, TableLookupResult] = {}

        return ProgramMetadataEvidence(
            tables=self._resolve_tables(program=program, cache=cache),
            columns=self._resolve_columns(program=program, cache=cache),
        )

    def _resolve_tables(
        self,
        *,
        program: SQLProgram,
        cache: dict[str, TableLookupResult],
    ) -> tuple[TableMetadataResolution, ...]:
        requests: list[tuple[MetadataObjectRole, str]] = []
        seen: set[tuple[MetadataObjectRole, str]] = set()

        for scope in program.scope_analyses:
            for binding in scope.source_bindings:
                if binding.kind is not SourceBindingKind.PHYSICAL_TABLE:
                    continue

                assert binding.physical_table is not None
                key = (MetadataObjectRole.READ_SOURCE, binding.physical_table)
                if key not in seen:
                    seen.add(key)
                    requests.append(key)

        for statement in program.statements:
            target = statement.write_target
            if target is None:
                continue

            key = (
                MetadataObjectRole.WRITE_TARGET,
                target.table_name.strip().lower(),
            )
            if key not in seen:
                seen.add(key)
                requests.append(key)

        return tuple(
            self._resolve_table_identifier(
                role=role,
                requested_table=table_name,
                lookup_cache=cache,
            )
            for role, table_name in requests
        )

    def _resolve_table_identifier(
        self,
        *,
        role: MetadataObjectRole,
        requested_table: str,
        lookup_cache: dict[str, TableLookupResult],
    ) -> TableMetadataResolution:
        normalized = requested_table.strip().lower()

        if not normalized:
            return TableMetadataResolution(
                role=role,
                requested_table=normalized,
                status=TableResolutionStatus.ABSENT,
            )

        # 已带 project / namespace：权威 exact lookup，不做 fallback。
        if "." in normalized:
            return self._table_lookup_to_resolution(
                role=role,
                requested_table=normalized,
                canonical_table=normalized,
                result=self._lookup(
                    table_name=normalized,
                    cache=lookup_cache,
                ),
            )

        # 裸表名：从完整 Metadata 中取得全部 exact base-name candidates。
        candidates = self._catalog.find_table_identifiers(normalized)
        candidate_names = tuple(
            sorted({candidate.full_name.lower() for candidate in candidates})
        )

        if not candidate_names:
            return TableMetadataResolution(
                role=role,
                requested_table=normalized,
                status=TableResolutionStatus.ABSENT,
            )

        if len(candidate_names) > 1:
            return TableMetadataResolution(
                role=role,
                requested_table=normalized,
                status=TableResolutionStatus.AMBIGUOUS,
                candidates=candidate_names,
            )

        canonical = candidate_names[0]
        result = self._lookup(table_name=canonical, cache=lookup_cache)

        if result.status is not MetadataLookupStatus.FOUND or result.table is None:
            return TableMetadataResolution(
                role=role,
                requested_table=normalized,
                status=TableResolutionStatus.ERROR,
                canonical_table=canonical,
                error_message=(
                    "MetadataCatalog resolved "
                    f"{normalized!r} to {canonical!r}, but MetadataProvider "
                    "could not load the canonical table."
                ),
            )

        return TableMetadataResolution(
            role=role,
            requested_table=normalized,
            status=TableResolutionStatus.RESOLVED,
            canonical_table=canonical,
            metadata=result.table,
        )

    @staticmethod
    def _table_lookup_to_resolution(
        *,
        role: MetadataObjectRole,
        requested_table: str,
        canonical_table: str,
        result: TableLookupResult,
    ) -> TableMetadataResolution:
        if result.status is MetadataLookupStatus.ERROR:
            return TableMetadataResolution(
                role=role,
                requested_table=requested_table,
                status=TableResolutionStatus.ERROR,
                canonical_table=canonical_table,
                error_message=result.error_message,
            )

        if result.status is MetadataLookupStatus.NOT_FOUND:
            return TableMetadataResolution(
                role=role,
                requested_table=requested_table,
                status=TableResolutionStatus.ABSENT,
            )

        if result.table is None:
            raise RuntimeError(
                "MetadataProvider returned FOUND without TableMetadata."
            )

        return TableMetadataResolution(
            role=role,
            requested_table=requested_table,
            status=TableResolutionStatus.RESOLVED,
            canonical_table=result.table.full_name,
            metadata=result.table,
        )

    def _resolve_columns(
        self,
        *,
        program: SQLProgram,
        cache: dict[str, TableLookupResult],
    ) -> tuple[ColumnMetadataResolution, ...]:
        resolutions: list[ColumnMetadataResolution] = []

        for scope in program.scope_analyses:
            for column in scope.facts.column_references:
                resolutions.append(
                    self._resolve_column(
                        scope=scope,
                        column=column,
                        cache=cache,
                    )
                )

        return tuple(resolutions)

    def _resolve_column(
        self,
        *,
        scope: ProgramScopeAnalysis,
        column: ColumnReference,
        cache: dict[str, TableLookupResult],
    ) -> ColumnMetadataResolution:
        if column.qualifier is None:
            return self._resolve_unqualified_column(
                scope=scope,
                column=column,
                lookup_cache=cache,
            )

        binding = self._resolve_qualified_binding(scope=scope, column=column)

        if binding is None:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.UNRESOLVED_SOURCE,
            )

        return self._resolve_column_from_binding(
            scope=scope,
            column=column,
            binding=binding,
            lookup_cache=cache,
        )

    def _resolve_unqualified_column(
        self,
        *,
        scope: ProgramScopeAnalysis,
        column: ColumnReference,
        lookup_cache: dict[str, TableLookupResult],
    ) -> ColumnMetadataResolution:
        resolved_candidates: list[
            tuple[ScopeSourceBinding, TableMetadata, ColumnMetadata]
        ] = []

        ambiguous_tables: set[str] = set()
        absent_sources: set[str] = set()
        has_non_physical_source = False
        has_unresolved_source = False

        for binding in scope.source_bindings:
            if binding.kind is SourceBindingKind.SCOPE:
                has_non_physical_source = True
                continue

            if binding.kind is SourceBindingKind.UNRESOLVED:
                has_unresolved_source = True
                continue

            assert binding.physical_table is not None

            table_resolution = self._resolve_table_identifier(
                role=MetadataObjectRole.READ_SOURCE,
                requested_table=binding.physical_table,
                lookup_cache=lookup_cache,
            )

            if table_resolution.status is TableResolutionStatus.ERROR:
                return ColumnMetadataResolution(
                    scope_id=scope.scope_id,
                    column=column,
                    status=ColumnResolutionStatus.SOURCE_ERROR,
                    source_alias=binding.alias,
                    error_message=table_resolution.error_message,
                )

            if table_resolution.status is TableResolutionStatus.AMBIGUOUS:
                ambiguous_tables.update(table_resolution.candidates)
                continue

            if table_resolution.status is TableResolutionStatus.ABSENT:
                absent_sources.add(binding.physical_table)
                continue

            table = table_resolution.metadata
            if table is None:
                raise RuntimeError(
                    "RESOLVED table resolution has no TableMetadata."
                )

            column_metadata = table.get_column(column.name)
            if column_metadata is not None:
                resolved_candidates.append((binding, table, column_metadata))

        if ambiguous_tables:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.SOURCE_AMBIGUOUS,
                candidate_tables=tuple(sorted(ambiguous_tables)),
            )

        if absent_sources:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.SOURCE_ABSENT,
                candidate_tables=tuple(sorted(absent_sources)),
            )

        if len(resolved_candidates) > 1:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.AMBIGUOUS,
                candidate_tables=tuple(
                    sorted(table.full_name for _, table, _ in resolved_candidates)
                ),
            )

        if len(resolved_candidates) == 1:
            binding, table, column_metadata = resolved_candidates[0]

            # 还有 CTE / derived / unresolved source 时，Physical Metadata
            # 无法单独证明该字段只属于这个物理表，留给 4.5 lineage。
            if has_non_physical_source or has_unresolved_source:
                return ColumnMetadataResolution(
                    scope_id=scope.scope_id,
                    column=column,
                    status=ColumnResolutionStatus.UNRESOLVED_SOURCE,
                    physical_table=table.full_name,
                    error_message=(
                        "A physical metadata candidate exists, but the scope also "
                        "contains non-physical or unresolved sources."
                    ),
                )

            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.RESOLVED,
                source_alias=binding.alias,
                physical_table=table.full_name,
                metadata=column_metadata,
            )

        if has_non_physical_source or has_unresolved_source:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.UNRESOLVED_SOURCE,
            )

        # 只有在没有物理候选时，才把显式 SELECT alias 作为 alias 事实。
        # 这样不会优先把同名真实字段误判成 alias。
        if column.name in scope.facts.select_aliases:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.SELECT_ALIAS,
            )

        return ColumnMetadataResolution(
            scope_id=scope.scope_id,
            column=column,
            status=ColumnResolutionStatus.ABSENT,
        )

    def _resolve_column_from_binding(
        self,
        *,
        scope: ProgramScopeAnalysis,
        column: ColumnReference,
        binding: ScopeSourceBinding,
        lookup_cache: dict[str, TableLookupResult],
    ) -> ColumnMetadataResolution:
        if binding.kind is SourceBindingKind.UNRESOLVED:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.UNRESOLVED_SOURCE,
                source_alias=binding.alias,
                error_message=binding.unresolved_reason,
            )

        if binding.kind is SourceBindingKind.SCOPE:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.NON_PHYSICAL_SOURCE,
                source_alias=binding.alias,
                source_scope_id=binding.source_scope_id,
            )

        assert binding.physical_table is not None

        table_resolution = self._resolve_table_identifier(
            role=MetadataObjectRole.READ_SOURCE,
            requested_table=binding.physical_table,
            lookup_cache=lookup_cache,
        )

        if table_resolution.status is TableResolutionStatus.ERROR:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.SOURCE_ERROR,
                source_alias=binding.alias,
                error_message=table_resolution.error_message,
            )

        if table_resolution.status is TableResolutionStatus.AMBIGUOUS:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.SOURCE_AMBIGUOUS,
                source_alias=binding.alias,
                candidate_tables=table_resolution.candidates,
            )

        if table_resolution.status is TableResolutionStatus.ABSENT:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.SOURCE_ABSENT,
                source_alias=binding.alias,
                physical_table=binding.physical_table,
            )

        table = table_resolution.metadata
        if table is None:
            raise RuntimeError("RESOLVED table resolution has no TableMetadata.")

        column_metadata = table.get_column(column.name)
        if column_metadata is None:
            return ColumnMetadataResolution(
                scope_id=scope.scope_id,
                column=column,
                status=ColumnResolutionStatus.ABSENT,
                source_alias=binding.alias,
                physical_table=table.full_name,
            )

        return ColumnMetadataResolution(
            scope_id=scope.scope_id,
            column=column,
            status=ColumnResolutionStatus.RESOLVED,
            source_alias=binding.alias,
            physical_table=table.full_name,
            metadata=column_metadata,
        )

    @staticmethod
    def _resolve_qualified_binding(
        *,
        scope: ProgramScopeAnalysis,
        column: ColumnReference,
    ) -> ScopeSourceBinding | None:
        qualifier = (column.qualifier or "").strip().lower()
        if not qualifier:
            return None

        for binding in scope.source_bindings:
            if binding.alias == qualifier:
                return binding

        return None

    def _lookup(
        self,
        *,
        table_name: str,
        cache: dict[str, TableLookupResult],
    ) -> TableLookupResult:
        normalized = table_name.strip().lower()
        cached = cache.get(normalized)
        if cached is not None:
            return cached

        result = self._provider.get_table(normalized)
        cache[normalized] = result
        return result
