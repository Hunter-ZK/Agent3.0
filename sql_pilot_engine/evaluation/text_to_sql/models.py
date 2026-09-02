from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


InitialBehavior = Literal[
    "result",
    "clarification",
]


class EvaluationFailureType(
    str,
    Enum,
):
    """
    Evaluation V2 冻结的失败七分类。

    一个失败最终只能归入一个主分类。
    """

    ASSET_DEFECT = (
        "asset_defect"
    )

    PLANNING_ERROR = (
        "planning_error"
    )

    LINKING_ERROR = (
        "linking_error"
    )

    GENERATION_ERROR = (
        "generation_error"
    )

    GATE_FALSE_POSITIVE = (
        "gate_false_positive"
    )

    GATE_FALSE_NEGATIVE = (
        "gate_false_negative"
    )

    SYSTEM_ERROR = (
        "system_error"
    )


@dataclass(frozen=True)
class TextToSQLEvalCase:
    """
    一个 Text-to-SQL Golden Case。
    """

    case_id: str

    question: str

    expected_initial: (
        InitialBehavior
    )

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

    def __post_init__(
        self,
    ) -> None:

        if not self.case_id.strip():
            raise ValueError(
                "case_id cannot be empty"
            )

        if not self.question.strip():
            raise ValueError(
                "question cannot be empty"
            )


@dataclass(frozen=True)
class TextToSQLEvalResult:
    """
    一次真实运行的 Evaluation V2 结果。

    六层：

        planning
        schema_link
        generation
        gate
        semantic
        final

    clarification_pass 单独记录 Agent 行为，
    不算第七层。
    """

    case_id: str

    run_index: int

    initial_behavior: str

    clarification_pass: bool

    planning_pass: bool

    schema_link_pass: bool

    generation_pass: bool

    gate_pass: bool

    semantic_pass: bool

    final_pass: bool

    system_error: bool

    failure_type: (
        EvaluationFailureType
        | None
    )

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

    generation_source: (
        str | None
    ) = None

    compilation_status: (
        str | None
    ) = None

    compilation_fallback_reason: (
        str | None
    ) = None

    linking_failure_codes: (
        tuple[str, ...]
    ) = ()

    validation_rule_ids: (
        tuple[str, ...]
    ) = ()

    evidence_rule_hits: (
        tuple[str, ...]
    ) = ()