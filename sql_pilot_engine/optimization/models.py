from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class OptimizationSuggestion:
    """一项 SQL 优化建议；它不是 Review Issue，也不是性能承诺。"""

    category: str
    priority: str
    description: str
    reason: str
    expected_benefit: str = ""
    risk: str = ""
    requires_execution_validation: bool = False


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """
    OptimizeService 的内部结果。

    candidate_sql 只是候选；opportunities 保存“为什么值得优化”的前置分析；validation 保存
    Program / Review 等后置 Gate。没有 Statistics / Execution 证据时不得把 expected benefit 当成
    已验证性能收益。
    """

    original_sql: str
    summary: str
    suggestions: tuple[OptimizationSuggestion, ...] = ()
    candidate_sql: str | None = None
    rewrite_reason: str | None = None
    assumptions: tuple[str, ...] = ()
    confidence: float = 0.0
    opportunities: tuple[dict[str, Any], ...] = ()
    validation: dict[str, Any] = field(default_factory=dict, compare=False)
    raw_output: dict[str, Any] = field(
        default_factory=dict,
        compare=False,
        repr=False,
    )
