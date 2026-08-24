from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InitialBehavior = Literal[
    "result",
    "clarification",
]


@dataclass(frozen=True)
class TextToSQLEvalCase:
    """一个 Text-to-SQL 评估用例。"""

    case_id: str
    question: str

    expected_initial: InitialBehavior

    clarification_answer: (
        str | None
    ) = None

    expected_tables: (
        tuple[str, ...]
    ) = ()

    expected_metrics: (
        tuple[str, ...]
    ) = ()

    expected_dimensions: (
        tuple[str, ...]
    ) = ()

    expected_group_by: (
        tuple[str, ...]
    ) = ()

    required_filter_terms: (
        tuple[str, ...]
    ) = ()


@dataclass(frozen=True)
class TextToSQLEvalResult:
    """一次真实运行的分层评分结果。"""

    case_id: str
    run_index: int

    initial_behavior: str

    planning_pass: bool
    clarification_pass: bool
    sql_trust_pass: bool
    semantic_pass: bool
    final_pass: bool

    system_error: bool

    validation_status: (
        str | None
    )

    semantic_status: (
        str | None
    )

    validation_error: (
        str | None
    )

    generated_sql: (
        str | None
    )

    trusted_sql: (
        str | None
    )

    reason: str