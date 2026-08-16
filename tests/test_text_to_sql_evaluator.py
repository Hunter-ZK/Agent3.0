from types import SimpleNamespace

import pytest

from sql_pilot_engine.evaluation.models import (
    GoldenTextToSQLCase,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
)


def build_actual_result(
    *,
    question: str,
    tables: tuple[str, ...],
    dimensions: tuple[str, ...],
    metrics: tuple[str, ...],
    group_by: tuple[str, ...],
    success: bool = True,
    trusted_sql: str | None = (
        "SELECT 1"
    ),
    validation_status: str = (
        "no_issue"
    ),
):
    plan = SimpleNamespace(
        tables=tables,
        dimensions=dimensions,
        metrics=metrics,
        group_by=group_by,
    )

    return SimpleNamespace(
        question=question,
        query_plan=plan,
        success=success,
        trusted_sql=trusted_sql,
        validation_status=(
            validation_status
        ),
    )


def test_perfect_case_passes() -> None:
    evaluator = TextToSQLEvaluator()

    case = GoldenTextToSQLCase(
        case_id="case-001",
        question=(
            "统计每个用户订单总金额"
        ),
        expected_tables=(
            "dwd_order_detail",
        ),
        expected_dimensions=(
            "user_id",
        ),
        expected_metrics=(
            "total_order_amount",
        ),
        expected_group_by=(
            "user_id",
        ),
    )

    actual = build_actual_result(
        question=case.question,
        tables=(
            "dwd_order_detail",
        ),
        dimensions=(
            "user_id",
        ),
        metrics=(
            "total_order_amount",
        ),
        group_by=(
            "user_id",
        ),
    )

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert result.passed is True
    assert (
        result.table_selection_correct
        is True
    )
    assert (
        result.metric_selection_correct
        is True
    )


def test_extra_table_fails_table_selection():
    evaluator = TextToSQLEvaluator()

    case = GoldenTextToSQLCase(
        case_id="case-002",
        question="统计订单金额",
        expected_tables=(
            "dwd_order_detail",
        ),
        expected_metrics=(
            "total_order_amount",
        ),
    )

    actual = build_actual_result(
        question=case.question,
        tables=(
            "dwd_order_detail",
            "dim_user",
        ),
        dimensions=(),
        metrics=(
            "total_order_amount",
        ),
        group_by=(),
    )

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert (
        result.table_selection_correct
        is False
    )
    assert result.passed is False


def test_missing_trusted_sql_fails():
    evaluator = TextToSQLEvaluator()

    case = GoldenTextToSQLCase(
        case_id="case-003",
        question="统计订单金额",
        expected_tables=(
            "dwd_order_detail",
        ),
        expected_metrics=(
            "total_order_amount",
        ),
    )

    actual = build_actual_result(
        question=case.question,
        tables=(
            "dwd_order_detail",
        ),
        dimensions=(),
        metrics=(
            "total_order_amount",
        ),
        group_by=(),
        success=False,
        trusted_sql=None,
        validation_status="blocked",
    )

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert (
        result.trusted_sql_available
        is False
    )
    assert result.passed is False


def test_question_mismatch_is_rejected():
    evaluator = TextToSQLEvaluator()

    case = GoldenTextToSQLCase(
        case_id="case-004",
        question="问题A",
        expected_tables=("table_a",),
    )

    actual = build_actual_result(
        question="问题B",
        tables=("table_a",),
        dimensions=(),
        metrics=(),
        group_by=(),
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        evaluator.evaluate(
            case=case,
            actual=actual,
        )


def test_summary_calculates_rates():
    evaluator = TextToSQLEvaluator()

    results = [
        SimpleNamespace(
            passed=True,
            table_selection_correct=True,
            dimension_selection_correct=True,
            metric_selection_correct=True,
            group_by_correct=True,
            pipeline_success=True,
            trusted_sql_available=True,
        ),
        SimpleNamespace(
            passed=False,
            table_selection_correct=False,
            dimension_selection_correct=True,
            metric_selection_correct=False,
            group_by_correct=True,
            pipeline_success=True,
            trusted_sql_available=True,
        ),
    ]

    summary = evaluator.summarize(
        results
    )

    assert summary.total_cases == 2
    assert summary.pass_rate == 0.5

    assert (
        summary.table_selection_accuracy
        == 0.5
    )

    assert (
        summary.dimension_selection_accuracy
        == 1.0
    )

    assert (
        summary.metric_selection_accuracy
        == 0.5
    )

    assert summary.trusted_sql_rate == 1.0