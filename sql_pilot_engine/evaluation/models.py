from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExpectedAgentBehavior(
    str,
    Enum,
):
    """Golden Case期望Agent采取的行为。"""

    ANSWER = "answer"
    CLARIFY = "clarify"


class ActualAgentBehavior(
    str,
    Enum,
):
    """Agent真实运行产生的行为。"""

    ANSWER = "answer"
    CLARIFY = "clarify"
    ERROR = "error"


@dataclass(
    frozen=True,
    slots=True,
)
class GoldenTextToSQLCase:
    """一条Agent / Text-to-SQL Golden Case。"""

    case_id: str
    question: str

    expected_behavior: ExpectedAgentBehavior = (
        ExpectedAgentBehavior.ANSWER
    )

    expected_tables: tuple[str, ...] = ()
    expected_dimensions: tuple[str, ...] = ()
    expected_metrics: tuple[str, ...] = ()
    expected_filters: tuple[str, ...] = ()
    expected_group_by: tuple[str, ...] = ()

    expected_trusted_sql: bool = True

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError(
                "case_id must not be empty"
            )

        if not self.question.strip():
            raise ValueError(
                "question must not be empty"
            )

        if (
            self.expected_behavior
            is ExpectedAgentBehavior.ANSWER
            and not self.expected_tables
        ):
            raise ValueError(
                "ANSWER case must define "
                "expected_tables"
            )

        if (
            self.expected_behavior
            is ExpectedAgentBehavior.CLARIFY
            and self.expected_trusted_sql
        ):
            raise ValueError(
                "CLARIFY case cannot expect "
                "trusted SQL"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLEvaluation:
    """单条Golden Case评分结果。"""

    case_id: str

    expected_behavior: ExpectedAgentBehavior
    actual_behavior: ActualAgentBehavior
    behavior_correct: bool

    actual_tables: tuple[str, ...] = ()
    actual_dimensions: tuple[str, ...] = ()
    actual_metrics: tuple[str, ...] = ()
    actual_filters: tuple[str, ...] = ()
    actual_group_by: tuple[str, ...] = ()

    # 对CLARIFY Case，
    # SQL Planning相关评分不适用，因此为None。
    table_selection_correct: bool | None = None
    dimension_selection_correct: bool | None = None
    metric_selection_correct: bool | None = None
    filter_selection_correct: bool | None = None
    group_by_correct: bool | None = None

    pipeline_success: bool | None = None

    trusted_sql_available: bool | None = None
    trusted_sql_expectation_met: bool | None = None

    validation_status: str | None = None
    semantic_validation_status: str | None = None

    passed: bool = False

    clarification_question: str | None = None
    error_message: str | None = None
    



@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLEvaluationSummary:
    """一组Agent / Text-to-SQL评测结果的汇总。"""

    total_cases: int

    answer_cases: int
    clarification_cases: int
    error_cases: int

    pass_rate: float
    error_rate: float

    # 所有Case参与。
    behavior_accuracy: float

    # 以下只统计适用的ANSWER Case。
    table_selection_accuracy: float
    dimension_selection_accuracy: float
    metric_selection_accuracy: float
    filter_selection_accuracy: float
    group_by_accuracy: float

    pipeline_success_rate: float
    trusted_sql_rate: float
    
    
class EvaluationFailureType(
    str,
    Enum,
):
    BEHAVIOR = "behavior"
    TABLE_SELECTION = "table_selection"
    DIMENSION_SELECTION = "dimension_selection"
    METRIC_SELECTION = "metric_selection"
    FILTER_SELECTION = "filter_selection"
    GROUP_BY = "group_by"
    PIPELINE = "pipeline"
    TRUSTED_SQL = "trusted_sql"
    ERROR = "error"