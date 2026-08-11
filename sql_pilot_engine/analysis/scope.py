from __future__ import annotations


from dataclasses import dataclass

from enum import Enum

from sqlglot import exp
from sqlglot.optimizer.scope import (
    Scope,
    ScopeType,
    traverse_scope,
)

from sql_pilot_engine.analysis.sql_parser import SQLParseResult



class ScopeKind(str, Enum):
    """DataAgent内部稳定的SQL作用域类型。

    为什么不直接向上层暴露SQLGlot ScopeType：
    后续Metadata、Lineage、Rule等模块应依赖
    项目自己的领域模型，而不是绑定第三方库。
    """
    
    ROOT = "root"
    SUBQUERY = "subquery"
    DERIVED_TABLE = "derived_table"
    CTE = "cte"
    UNION = "union"
    UDTF = "udtf"
    UNKNOWN = "unknown"
    
class ScopeSourceKind(str, Enum):
    """当前Scope中一个可见数据源的类型。"""

    PHYSICAL_TABLE = "physical_table"
    CTE = "cte"
    DERIVED_TABLE = "derived_table"
    SUBQUERY = "subquery"
    UNION = "union"
    UDTF = "udtf"
    UNKNOWN = "unknown"
    

@dataclass(frozen=True)
class ScopeSource:
    """当前查询层能够通过某个名称访问的数据源。

    示例：

    FROM dwd_order_detail o
    → name="o"
    → kind=PHYSICAL_TABLE
    → physical_name="dwd_order_detail"

    FROM order_summary o
    → name="o"
    → kind=CTE
    → source_scope_id指向CTE对应Scope
    """
    
    name: str
    kind: ScopeSourceKind

    physical_name: str | None = None
    source_scope_id: str | None = None
    

@dataclass(frozen=True)
class ScopeColumnReference:
    """某个具体Scope中的一次字段引用。

    与SQLFacts.ColumnReference不同：
    SQLFacts是整条SQL汇总；
    本对象明确属于某个Scope。

    tuple中不主动去重，因为：
    SELECT a FROM t WHERE a > 1
    中两次a是两个真实引用。
    """
    
    name: str
    qualifier: str | None = None


@dataclass(frozen=True)
class ScopeProjection:
    """一个Scope对外输出的字段。

    示例：
        SUM(order_amount) AS total_amount

    表示：
        output_name = total_amount
        expression_sql = SUM(order_amount)
        source_columns = (order_amount,)
    """
    output_name: str
    expression_sql: str
    source_columns: tuple[ScopeColumnReference,...]
    

@dataclass(frozen=True)
class ScopeInfo:
    """DataAgent内部的单个SQL作用域。"""
    
    scope_id: str
    statement_index: int
    
    parent_scope_id: str | None
    kind: ScopeKind
    
    expression_sql: str
    
    sources: tuple[ScopeSource, ...]
    columns: tuple[ScopeColumnReference, ...]
    output_columns: tuple[str, ...]
    projections: tuple[ScopeProjection, ...]
    
    is_correlated: bool = False
    
    
@dataclass(frozen=True)
class ScopeAnalysisResult:
    
    scopes: tuple[ScopeInfo, ...]
    
    def scopes_for_statement(
        self,
        statement_index: int,
    ) -> tuple[ScopeInfo, ...]:
        return tuple(
            scope
            for scope in self.scopes
            if scope.statement_index == statement_index
        )
        

class SQLScopeAnalyzer:
    """将SQLGlot Scope转换成DataAgent稳定Scope模型。

    输入：
        SQLParser已经产生的SQLParseResult。

    输出：
        ScopeAnalysisResult。

    它不重新解析SQL，也不访问Metadata。
    """
    
    def analyze(
        self,
        parse_result: SQLParseResult,
    ) -> ScopeAnalysisResult:
        if not parse_result.success:
            raise ValueError(
                "Cannot analyze scope from "
                "a failed parse result."
            )
            
        result: list[ScopeInfo] = []
        
        for statement_index, statement in enumerate(parse_result.statements):
            
            sqlglot_scopes = traverse_scope(statement)
            
            scope_ids = {
                id(scope):(
                    f"s{statement_index}_q"
                    f"{scope_index}"
                )
                for scope_index, scope in enumerate(sqlglot_scopes)
            }
            
            for scope in sqlglot_scopes:
                result.append(
                    self._build_scope_info(
                        scope = scope,
                        statement_index = (statement_index),
                        scope_ids = scope_ids,
                    )
                )
        
        return ScopeAnalysisResult(scopes=tuple(result))
    
    def _build_scope_info(
        self,
        *,
        scope: Scope,
        statement_index: int,
        scope_ids: dict[int, str],
    ) -> ScopeInfo:
        scope_id = scope_ids[id(scope)]
        
        parent_scope_id = (
            scope_ids.get(id(scope.parent))
            if scope.parent is not None
            else None
        )
        
        sources = tuple(
            self._build_source(
                name = name,
                source = source,
                scope_ids = scope_ids,
            )
            for name, source
            in scope.sources.items()
        )
        
        columns = tuple(
            ScopeColumnReference(
                name=column.name.lower(),
                qualifier=(
                    column.table.lower()
                    if column.table
                    else None
                ),
            )
            for column in scope.columns
            if column.name and column.name != "*"
        )
        
        projections = self._extract_projections(scope)
        
        output_columns = self._extract_output_columns(scope)
        
        return ScopeInfo(
            scope_id=scope_id,
            statement_index=statement_index,
            parent_scope_id=parent_scope_id,
            kind=self._map_scope_kind(scope.scope_type),
            expression_sql=(scope.expression.sql()),
            sources=sources,
            columns=columns,
            output_columns=output_columns,
            projections=projections,
            is_correlated=scope.is_correlated_subquery,
        )
        
    def _build_source(
        self,
        *,
        name: str,
        source: exp.Table | Scope,
        scope_ids: dict[int, str],
    ) -> ScopeSource:
        
        visible_name = name.lower()
        
        if isinstance(source, exp.Table):
            return ScopeSource(
                name= visible_name,
                kind = (
                    ScopeSourceKind.PHYSICAL_TABLE
                ),
                physical_name=(self._qualified_table_name(source)),
            )
            
        if isinstance(source, Scope):
            return ScopeSource(
                name=visible_name,
                kind=self._map_source_kind(
                    source.scope_type
                ),
                source_scope_id=scope_ids.get(
                    id(source)
                ),
            )

        return ScopeSource(
            name=visible_name,
            kind=ScopeSourceKind.UNKNOWN,
        )
        
    @staticmethod
    def _extract_output_columns(
        scope: Scope,
    ) -> tuple[str, ...]:
        # SQL允许显式重命名派生表/CTE输出：
        #
        # WITH t(a, b) AS (
        #     SELECT x, y FROM source
        # )
        #
        # 这时外部真正看到的是a、b，而不是x、y。
        if scope.outer_columns:
            return tuple(
                name.lower()
                for name in scope.outer_columns
            )

        expression = scope.expression

        if not isinstance(expression, exp.Query):
            return ()

        return tuple(
            name.lower()
            for name in expression.named_selects
            if name and name != "*"
        )

    @staticmethod
    def _extract_projections(
        scope: Scope,
    ) -> tuple[ScopeProjection, ...]:
        
        expression = scope.expression
        
        if not isinstance(expression, exp.Query):
            return ()
        
        selects = expression.selects
        
        result: list[ScopeProjection] = []
        
        for index, projection in enumerate(selects):
            
            if index < len(scope.outer_columns):
                output_name = (scope.outer_columns[index].lower())
            else:
                output_name = (
                    projection.alias_or_name
                    or projection.output_name
                    or projection.sql()
                ).lower()
                
            source_columns = tuple(
                ScopeColumnReference(
                    name=column.name.lower(),
                    qualifier=(
                        column.table.lower()
                        if column.table
                        else None
                    ),
                    
                )
                for column
                in projection.find_all(exp.Column)
                if column.name and column.name != '*'
                and SQLScopeAnalyzer._column_belongs_to_projection_scope(
                    column = column,
                    scope_expressin=expression,
                )
            )
            
            result.append(
                ScopeProjection(
                    output_name=output_name,
                    expression_sql=projection.sql(),
                    source_columns=source_columns,
                )
            )
        
        return tuple(result)

    @staticmethod
    def _map_scope_kind(
        scope_type: ScopeType,
    ) -> ScopeKind:
        mapping = {
            ScopeType.ROOT:
                ScopeKind.ROOT,
            ScopeType.SUBQUERY:
                ScopeKind.SUBQUERY,
            ScopeType.DERIVED_TABLE:
                ScopeKind.DERIVED_TABLE,
            ScopeType.CTE:
                ScopeKind.CTE,
            ScopeType.UNION:
                ScopeKind.UNION,
            ScopeType.UDTF:
                ScopeKind.UDTF,
        }

        return mapping.get(
            scope_type,
            ScopeKind.UNKNOWN,
        )

    @staticmethod
    def _map_source_kind(
        scope_type: ScopeType,
    ) -> ScopeSourceKind:
        mapping = {
            ScopeType.CTE:
                ScopeSourceKind.CTE,
            ScopeType.DERIVED_TABLE:
                ScopeSourceKind.DERIVED_TABLE,
            ScopeType.SUBQUERY:
                ScopeSourceKind.SUBQUERY,
            ScopeType.UNION:
                ScopeSourceKind.UNION,
            ScopeType.UDTF:
                ScopeSourceKind.UDTF,
        }

        return mapping.get(
            scope_type,
            ScopeSourceKind.UNKNOWN,
        )

    @staticmethod
    def _qualified_table_name(
        table: exp.Table,
    ) -> str:
        parts = (
            table.catalog,
            table.db,
            table.name,
        )

        return ".".join(
            part.lower()
            for part in parts
            if part
        )
        
    
    @staticmethod
    def _column_belongs_to_projection_scope(
        *,
        column: exp.Column,
        scope_expression: exp.Expression,
    ) -> bool:
        """排除投影内部嵌套子查询中的字段。"""

        node = column.parent

        while node is not None:
            if node is scope_expression:
                return True

            if isinstance(node, exp.Query):
                return False

            node = node.parent

        return False