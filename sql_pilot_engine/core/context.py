# sql_review_agent/core/context.py

from dataclasses import dataclass
from typing import Any

from sql_pilot_engine.analysis.facts import SQLFacts
from sql_pilot_engine.analysis.sql_parser import SQLParseResult

@dataclass
class ReviewContext:
    """规则、LLM、元数据运行时上下文。"""

    mode: str = "prod"
    dialect: str = "maxcompute"
    
    parse_result: SQLParseResult | None = None
    
    sql_facts: SQLFacts | None = None
    
    metadata_provider: Any | None = None
    enable_llm: bool = False
    llm_provider: str = "mock"
    
    rule_packs: list[str] | None = None
    extra: dict[str, Any] | None = None
    
    
