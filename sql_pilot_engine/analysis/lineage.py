from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.analysis.scope import (
    ScopeAnalysisResult,
    ScopeInfo,
    ScopeSource,
    ScopeSourceKind,
)


@dataclass(frozen=True)
class PhysicalColumnSource:
    """已经追踪到物理表的最终字段来源。"""

    table_name: str
    column_name: str


@dataclass(frozen=True)
class ColumnLineage:
    """一个输出字段的轻量字段血缘。"""

    scope_id: str
    output_column: str
    expression_sql: str

    physical_sources: tuple[
        PhysicalColumnSource, ...
    ]

    unresolved_references: tuple[
        str, ...
    ] = ()
    
@dataclass(frozen=True)
class LineageAnalysisResult:
    columns: tuple[ColumnLineage, ...]
    

class SQLLineageAnalyzer:
    """基于Scope分析结果追踪第一版字段血缘。

    当前支持：
    - 物理表字段
    - CTE
    - Derived Table
    - 别名
    - 简单表达式
    - 聚合表达式

    当前不猜测：
    - 多数据源下未限定字段
    """
    
    def analyze(
        self,
        scope_analysis: ScopeAnalysisResult,
    ) -> LineageAnalysisResult:
        scope_map = {
            scope.scope_id: scope
            for scope in scope_analysis.scopes
        }
        
        result: list[ColumnLineage] = []
        
        for scope in scope_analysis.scopes:
            for projection in scope.projection:
                physical_sources = []
                unresolved = []
                
                for column in (projection.source_columns):
                    sources, failures = (
                        self._resolve_column(
                            scope=scope,
                            column_name=column.name,
                            qualifier=(column.qualifier),
                            scope_map=scope_map,
                            visited=set(),
                        )
                    )

                    physical_sources.extend(sources)

                    unresolved.extend(failures)

                result.append(
                    ColumnLineage(
                        scope_id=scope.scope_id,
                        output_column=(
                            projection.output_name
                        ),
                        expression_sql=(
                            projection.expression_sql
                        ),
                        physical_sources=tuple(
                            self._deduplicate_sources(
                                physical_sources
                            )
                        ),
                        unresolved_references=tuple(
                            dict.fromkeys(
                                unresolved
                            )
                        ),
                    )
                )

        return LineageAnalysisResult(
            columns=tuple(result)
        )

    def _resolve_column(
        self,
        *,
        scope: ScopeInfo,
        column_name: str,
        qualifier: str | None,
        scope_map: dict[str, ScopeInfo],
        visited: set[
            tuple[str, str]
        ],
    ) -> tuple[
        list[PhysicalColumnSource],
        list[str],
    ]:
        visit_key = (
            scope.scope_id,
            column_name,
        )

        if visit_key in visited:
            return [], [
                f"cyclic:{scope.scope_id}"
                f".{column_name}"
            ]

        visited = {
            *visited,
            visit_key,
        }

        if qualifier:
            source = self._find_source(
                scope,
                qualifier,
            )

            if source is None:
                return [], [
                    f"{qualifier}.{column_name}"
                ]

            return self._resolve_from_source(
                source=source,
                column_name=column_name,
                scope_map=scope_map,
                visited=visited,
            )

        # 未限定字段：
        # 单数据源可以安全解析；
        # 多数据源当前不能猜。
        if len(scope.sources) == 1:
            return self._resolve_from_source(
                source=scope.sources[0],
                column_name=column_name,
                scope_map=scope_map,
                visited=visited,
            )

        return [], [
            f"ambiguous:{column_name}"
        ]

    def _resolve_from_source(
        self,
        *,
        source: ScopeSource,
        column_name: str,
        scope_map: dict[str, ScopeInfo],
        visited: set[
            tuple[str, str]
        ],
    ):
        if (
            source.kind
            == ScopeSourceKind.PHYSICAL_TABLE
        ):
            if source.physical_name is None:
                return [], [
                    f"unknown:{column_name}"
                ]

            return [
                PhysicalColumnSource(
                    table_name=(
                        source.physical_name
                    ),
                    column_name=column_name,
                )
            ], []

        if source.source_scope_id is None:
            return [], [
                f"{source.name}.{column_name}"
            ]

        child_scope = scope_map.get(
            source.source_scope_id
        )

        if child_scope is None:
            return [], [
                f"{source.name}.{column_name}"
            ]

        projection = next(
            (
                item
                for item
                in child_scope.projections
                if item.output_name
                == column_name
            ),
            None,
        )

        if projection is None:
            return [], [
                f"{source.name}.{column_name}"
            ]

        physical_sources = []
        unresolved = []

        for child_column in (
            projection.source_columns
        ):
            sources, failures = (
                self._resolve_column(
                    scope=child_scope,
                    column_name=(
                        child_column.name
                    ),
                    qualifier=(
                        child_column.qualifier
                    ),
                    scope_map=scope_map,
                    visited=visited,
                )
            )

            physical_sources.extend(
                sources
            )
            unresolved.extend(
                failures
            )

        return (
            physical_sources,
            unresolved,
        )

    @staticmethod
    def _find_source(
        scope: ScopeInfo,
        name: str,
    ) -> ScopeSource | None:
        normalized = name.lower()

        return next(
            (
                source
                for source in scope.sources
                if source.name == normalized
            ),
            None,
        )

    @staticmethod
    def _deduplicate_sources(
        sources: list[
            PhysicalColumnSource
        ],
    ) -> list[PhysicalColumnSource]:
        seen = set()
        result = []

        for source in sources:
            key = (
                source.table_name,
                source.column_name,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(source)

        return result
