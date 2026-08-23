from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(
    frozen=True,
    slots=True,
)
class OptimizationSuggestion:
    """
    LLM 发现的一项 SQL 优化机会。

    它不是 Review Issue。
    SQL 可以完全可信，同时仍然存在 OptimizationSuggestion。
    """

    category: str
    priority: str

    description: str
    reason: str

    expected_benefit: str = ""
    risk: str = ""

    requires_execution_validation: bool = False


@dataclass(
    frozen=True,
    slots=True,
)
class OptimizationResult:
    """
    OptimizeService 的内部 Domain Result。

    candidate_sql 只是候选 SQL。
    是否采纳由 SQLAgentWorkflow 决定。
    """

    original_sql: str

    summary: str

    suggestions: tuple[
        OptimizationSuggestion,
        ...,
    ] = ()

    candidate_sql: str | None = None

    rewrite_reason: str | None = None

    assumptions: tuple[str, ...] = ()

    confidence: float = 0.0

    raw_output: dict[
        str,
        Any,
    ] = field(
        default_factory=dict,
        compare=False,
        repr=False,
    )