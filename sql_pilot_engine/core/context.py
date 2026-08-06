from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:
    from sql_pilot_engine.analysis.facts import (
        SQLFacts,
    )
    from sql_pilot_engine.analysis.sql_parser import (
        SQLParseResult,
    )
    from sql_pilot_engine.metadata.provider import (
        MetadataProvider,
    )


@dataclass
class ReviewContext:
    """规则和审查能力共享的单次运行上下文。

    Request：
        外部调用契约，只携带调用者提供的原始参数。

    ReviewContext：
        SQL解析完成后的内部上下文，保存AST解析结果、
        SQLFacts、元数据Provider等可复用对象。

    设计目的：
        保证SQL只解析一次，并让Rule、Metadata和后续Scope
        读取同一份可信分析结果。
    """

    mode: str = "prod"
    dialect: str = "maxcompute"

    parse_result: SQLParseResult | None = None
    sql_facts: SQLFacts | None = None

    metadata_provider: MetadataProvider | None = None

    enable_llm: bool = False
    llm_provider: str = "mock"

    rule_packs: list[str] | None = None
    extra: dict[str, Any] | None = None