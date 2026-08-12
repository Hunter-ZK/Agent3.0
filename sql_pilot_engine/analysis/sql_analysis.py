from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.analysis.sql_parser import (
    SQLParseResult,
    SQLParser,
)
from sql_pilot_engine.analysis.facts import (
    SQLFacts,
    SQLFactsExtractor,
)

@dataclass(frozen=True)
class SQLAnalysisResult:
    parse_result: SQLParseResult
    facts: SQLFacts | None
    
    @property
    def success(self) -> bool:
        return self.parse_result.success
    

class SQLAnalysisAdapter:
    def __init__(
        self,
        parser: SQLParser | None = None,
        facts_extractor: SQLFactsExtractor | None = None,
    ) -> None:
        
        self.parser = parser or SQLParser()
        self.facts_extractor = facts_extractor or SQLFactsExtractor()
        
    def analyze(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
    ) -> SQLAnalysisResult:
        
        parse_result = self.parser.parse(
            sql=sql,
            dialect=dialect,
        )

        if not parse_result.success:
            return SQLAnalysisResult(
                parse_result=parse_result,
                facts=None,
            )

        facts = self.facts_extractor.extract(
            parse_result=parse_result,
        )

        return SQLAnalysisResult(
            parse_result=parse_result,
            facts=facts,
        )