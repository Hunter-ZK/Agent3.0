from __future__ import annotations

import pytest

from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    ExpectedAgentBehavior,
    GoldenTextToSQLCase,
    TextToSQLEvaluation,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
)
from sql_pilot_engine.generation.models import (
    QueryPlan,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLResult,
)


def build_actual_result(
    *,
    question: str,
    tables: tuple[str, ...],
    dimensions: tuple[str, ...] = (),
    metrics: tuple[str, ...] = (),
    filters: tuple[str, ...] = (),
    group_by: tuple[str, ...] = (),
    success: bool = True,
    trusted_sql: str | None = "SELECT 1",
    validation_status: str = "no_issue",
    semantic_validation_status: str | None = (
        "pass"
    ),
) -> TextToSQLResult:
    """构造真实TextToSQLResult测试对象。

    不再使用SimpleNamespace，
    防止测试Fixture与正式DTO契约脱节。
    """

    return TextToSQLResult(
        question=question,

        query_plan=QueryPlan(
            tables=tables,
            dimensions=dimensions,
            metrics=metrics,
            filters=filters,
            group_by=group_by,
        ),

        generated_sql="SELECT 1",

        trusted_sql=trusted_sql,

        success=success,

        validation_status=(
            validation_status
        ),

        semantic_validation_status=(
            semantic_validation_status
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
        result.actual_behavior
        is ActualAgentBehavior.ANSWER
    )

    assert result.behavior_correct is True
    assert result.table_selection_correct is True
    assert result.metric_selection_correct is True


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

        metrics=(
            "total_order_amount",
        ),
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

        metrics=(
            "total_order_amount",
        ),

        success=False,
        trusted_sql=None,
        validation_status="blocked",

        semantic_validation_status=(
            "fail"
        ),
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
        expected_tables=(
            "table_a",
        ),
    )

    actual = build_actual_result(
        question="问题B",
        tables=(
            "table_a",
        ),
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        evaluator.evaluate(
            case=case,
            actual=actual,
        )


def test_clarification_case_passes():
    evaluator = TextToSQLEvaluator()

    case = GoldenTextToSQLCase(
        case_id="case-005",

        question="统计本期贷款余额",

        expected_behavior=(
            ExpectedAgentBehavior.CLARIFY
        ),

        expected_trusted_sql=False,
    )

    actual = TextToSQLClarification(
        question=case.question,

        clarification_question=(
            "请确认需要统计科技贷款"
            "还是绿色贷款。"
        ),

        missing_context=(
            "贷款业务主题",
        ),

        reason=(
            "当前存在多个贷款业务主题。"
        ),
    )

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert result.passed is True

    assert (
        result.actual_behavior
        is ActualAgentBehavior.CLARIFY
    )

    assert result.behavior_correct is True

    assert (
        result.table_selection_correct
        is None
    )

    assert (
        result.metric_selection_correct
        is None
    )


def test_unnecessary_clarification_fails():
    evaluator = TextToSQLEvaluator()

    case = GoldenTextToSQLCase(
        case_id="case-006",

        question="统计本期绿色贷款余额",

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_metrics=(
            "green_loan_balance",
        ),
    )

    actual = TextToSQLClarification(
        question=case.question,

        clarification_question=(
            "请确认是哪种贷款。"
        ),
    )

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert result.behavior_correct is False
    assert result.passed is False


def test_summary_calculates_rates():
    evaluator = TextToSQLEvaluator()

    results = (
        TextToSQLEvaluation(
            case_id="case-001",

            expected_behavior=(
                ExpectedAgentBehavior.ANSWER
            ),

            actual_behavior=(
                ActualAgentBehavior.ANSWER
            ),

            behavior_correct=True,

            table_selection_correct=True,
            dimension_selection_correct=True,
            metric_selection_correct=True,
            filter_selection_correct=True,
            group_by_correct=True,

            pipeline_success=True,

            trusted_sql_available=True,
            trusted_sql_expectation_met=True,

            validation_status="no_issue",
            semantic_validation_status="pass",

            passed=True,
        ),

        TextToSQLEvaluation(
            case_id="case-002",

            expected_behavior=(
                ExpectedAgentBehavior.ANSWER
            ),

            actual_behavior=(
                ActualAgentBehavior.ANSWER
            ),

            behavior_correct=True,

            table_selection_correct=False,
            dimension_selection_correct=True,
            metric_selection_correct=False,
            filter_selection_correct=True,
            group_by_correct=True,

            pipeline_success=True,

            trusted_sql_available=True,
            trusted_sql_expectation_met=True,

            validation_status="no_issue",
            semantic_validation_status="pass",

            passed=False,
        ),
    )

    summary = evaluator.summarize(
        results
    )

    assert summary.total_cases == 2
    assert summary.answer_cases == 2
    assert summary.clarification_cases == 0

    assert summary.pass_rate == 0.5
    assert summary.behavior_accuracy == 1.0

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

    assert (
        summary.filter_selection_accuracy
        == 1.0
    )

    assert (
        summary.group_by_accuracy
        == 1.0
    )

    assert (
        summary.trusted_sql_rate
        == 1.0
    )


def test_summary_excludes_clarify_from_sql_accuracy():
    evaluator = TextToSQLEvaluator()

    results = (
        TextToSQLEvaluation(
            case_id="answer",

            expected_behavior=(
                ExpectedAgentBehavior.ANSWER
            ),

            actual_behavior=(
                ActualAgentBehavior.ANSWER
            ),

            behavior_correct=True,

            table_selection_correct=True,
            dimension_selection_correct=True,
            metric_selection_correct=True,
            filter_selection_correct=True,
            group_by_correct=True,

            pipeline_success=True,

            trusted_sql_available=True,
            trusted_sql_expectation_met=True,

            validation_status="no_issue",
            semantic_validation_status="pass",

            passed=True,
        ),

        TextToSQLEvaluation(
            case_id="clarify",

            expected_behavior=(
                ExpectedAgentBehavior.CLARIFY
            ),

            actual_behavior=(
                ActualAgentBehavior.CLARIFY
            ),

            behavior_correct=True,

            table_selection_correct=None,
            dimension_selection_correct=None,
            metric_selection_correct=None,
            filter_selection_correct=None,
            group_by_correct=None,

            pipeline_success=None,

            trusted_sql_available=None,
            trusted_sql_expectation_met=None,

            validation_status=None,
            semantic_validation_status=None,

            passed=True,

            clarification_question=(
                "请确认贷款业务主题。"
            ),
        ),
    )

    summary = evaluator.summarize(
        results
    )

    assert summary.total_cases == 2
    assert summary.behavior_accuracy == 1.0

    # CLARIFY Case不会进入SQL指标分母。
    assert (
        summary.table_selection_accuracy
        == 1.0
    )

    assert (
        summary.metric_selection_accuracy
        == 1.0
    )

    assert (
        summary.filter_selection_accuracy
        == 1.0
    )