from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SQLAnalysisResult:
    """
    Agent3.0 内部统一 SQL 分析结果。

    注意：
    这里不是 SQL AST。

    SQLGlot 负责解析。
    Agent3.0 只保存业务需要的信息。
    """
    
    tables: list[str]
    
    columns; list[str]
    
    joins: list[str]
    
    statements: list[str]
    

class SQLAnalysisFacade:
    
    def __init__(
        self,
        adapter,
    ):
        self.adapter = adapter
        
    
    def analyze(
        self,
        sql: str,
        dialect: str = "dops",
    ) -> SQLAnalysisResult:
        
        facts = self.adapter.analyze(
            sql,
            dialect=dialect,
        )
        
        return SQLAnalysisResult(
            tables=facts.tables,
            columns=facts.columns,
            joins=facts.joins,
            statements=facts.statements,
        )