from __future__ import annotations
from dataclasses import dataclass

from sqlglot import exp

from sqlglot.optimizer.scope import traverse_scope

from sql_pilot_engine.analysis.scope import ScopeAnalysisResult

from sql_pilot_engine.analysis.sql_parser import SQLParseResult


@dataclass(frozen=True)
class JoinReference:
    """单个查询作用域中的一次Join关系。"""

    statement_index: int
    scope_id: str

    left_sources: tuple[str, ...]
    right_source: str

    join_type: str

    condition_sql: str | None
    using_columns: tuple[str, ...]
    
    @property
    def has_condition(self) -> bool:
        return bool(
            self.condition_sql 
            or self.using_columns
        )
        

@dataclass(frozen=True)
class JoinAnalysisResult:
    joins: tuple[JoinReference, ...]
    
    

class SQLJoinAnalyzer:
    """从已有AST提取Join结构。

    注意：
    这里再次遍历AST，不是重新parse SQL。
    """
    
    def analyze(
        self,
        *,
        parse_result: SQLParseResult,
        scope_analysis: ScopeAnalysisResult,
    ) -> JoinAnalysisResult:
        
        if not parse_result.success:
            raise ValueError(
                "Cannot analyze joins from "
                "failed parse result."
            )
            
        joins: list[JoinReference] = []
        
        for statement_index, statement in enumerate(
            parse_result.statements
        ):
            sqlglot_scopes = traverse_scope(statement)
            
            scope_infos = scope_analysis.scopes_for_statement(statement_index)
            
            if len(sqlglot_scopes) != len(scope_infos):
                raise RuntimeError(
                    "Scope analysis is inconsistent "
                    "with SQLGlot scope traversal."
                )
                
            for sqlglot_scope, scope_info in zip(
                sqlglot_scopes, scope_infos
            ):
                joins.extend(
                    self._extract_scope_joins(
                        sqlglot_scope.expression,
                        statement_index,
                        scope_info.scope_id,
                    )
                )
        
        return JoinAnalysisResult(
            joins=tuple(joins)
        )
        
    def _extract_scope_joins(
        self,
        expression: exp.Expression,
        statement_index: int,
        scope_id: str,
    ) -> list[JoinReference]:
        join_nodes = (
            expression.args.get("joins")
            or []
        )
        
        if not join_nodes:
            return []
        
        from_expression = (
            expression.args.get("from_")
            or expression.args.get("from")
        )
        
        if from_expression is None:
            return []
        
        first_source = self._source_name(
            from_expression.this
        )
        
        if not first_source:
            return []
        
        accumulated_sources = [
            first_source
        ]
        
        result: list[JoinReference] = []
        
        for join in join_nodes:
            right_source = self._source_name(
                join.this
            )
            
            if not right_source:
                continue
            
            on_expression = join.args.get("on")
            
            using_expressions = (
                join.args.get("using")
                or []
            )
            
            result.append(
                JoinReference(
                    statement_index=(
                        statement_index
                    ),
                    scope_id=scope_id,
                    left_sources=tuple(
                        accumulated_sources
                    ),
                    right_source=right_source,
                    join_type=self._join_type(join),
                    condition_sql=(
                        on_expression.sql()
                        if on_expression
                        else None
                    ),
                    using_columns=tuple(
                        item.name.lower()
                        for item in using_expressions
                        if item.name
                    ),
                    
                )
            )
            
            accumulated_sources.append(
                right_source
            )
        return result
    
    @staticmethod
    def _source_name(
        source: exp.Expression | None,
    ) -> str | None:
        if source is None:
            return None
        
        name = source.alias_or_name
        
        return (
            name.lower()
            if name
            else None
        )
        
    
    @staticmethod
    def _join_type(
        join: exp.Join,
    ) -> str:
        side = str(
            join.args.get("side") or ""
        ).upper()

        kind = str(
            join.args.get("kind") or ""
        ).upper()

        if side and kind:
            return f"{side} {kind}"

        if side:
            return side

        if kind:
            return kind

        return "INNER"
        