from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class GoldenTextToSQLCase:
    """一条 Text-to-SQL Golden Case。

    它描述的不是“模型应该输出哪一段SQL”，
    而是“这个业务问题正确理解后应该包含什么语义”。
    """

    case_id: str
    question: str

    expected_tables: tuple[str, ...]
    expected_dimensions: tuple[str, ...] = ()
    expected_metrics: tuple[str, ...] = ()
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

        if not self.expected_tables:
            raise ValueError(
                "expected_tables must not be empty"
            )

@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLEvaluation:
    """单条 Golden Case 的评分结果。"""

    case_id: str

    table_selection_correct: bool
    dimension_selection_correct: bool
    metric_selection_correct: bool
    group_by_correct: bool

    pipeline_success: bool
    trusted_sql_available: bool
    trusted_sql_expectation_met: bool

    validation_status: str

    passed: bool


@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLEvaluationSummary:
    """一组评测结果的聚合指标。"""

    total_cases: int

    pass_rate: float

    table_selection_accuracy: float
    dimension_selection_accuracy: float
    metric_selection_accuracy: float
    group_by_accuracy: float

    pipeline_success_rate: float
    trusted_sql_rate: float