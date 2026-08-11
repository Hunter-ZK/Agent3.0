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