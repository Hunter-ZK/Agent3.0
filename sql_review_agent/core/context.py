# sql_review_agent/core/context.py

from dataclasses import dataclass
from typing import Any


@dataclass
class ReviewContext:
    """规则、LLM、元数据运行时上下文。"""

    mode: str = "prod"
    dialect: str = "maxcompute"
    metadata_provider: Any | None = None
    enable_llm: bool = False
    llm_provider: str = "mock"
    rule_packs: list[str] | None = None
    extra: dict[str, Any] | None = None
