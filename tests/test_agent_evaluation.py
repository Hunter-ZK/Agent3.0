from __future__ import annotations

from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    ExpectedAgentBehavior,
    GoldenTextToSQLCase,
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


def test_answer_case_passes():
    case = GoldenTextToSQLCase(
        case_id="answer_case",

        question=(
            "统计本期绿色贷款余额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=(
            "dt",
        ),

        expected_metrics=(
            "green_loan_balance",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "dt",
        ),

        expected_trusted_sql=True,
    )

    actual = TextToSQLResult(
        question=case.question,

        query_plan=QueryPlan(
            tables=(
                "dwd_hd_201_cldwdk",
            ),

            dimensions=(
                "dt",
            ),

            metrics=(
                "green_loan_balance",
            ),

            filters=(
                "dt = '${p_month_yyyymm}'",
            ),

            group_by=(
                "dt",
            ),
        ),

        generated_sql=(
            "SELECT "
            "SUM(loan_bal_rmb), dt "
            "FROM dwd_hd_201_cldwdk "
            "WHERE dt = '${p_month_yyyymm}' "
            "GROUP BY dt"
        ),

        trusted_sql=(
            "SELECT "
            "SUM(loan_bal_rmb), dt "
            "FROM dwd_hd_201_cldwdk "
            "WHERE dt = '${p_month_yyyymm}' "
            "GROUP BY dt"
        ),

        success=True,

        validation_status=(
            "no_issue"
        ),

        semantic_validation_status=(
            "pass"
        ),
    )

    evaluator = TextToSQLEvaluator()

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert (
        result.actual_behavior
        is ActualAgentBehavior.ANSWER
    )

    assert result.behavior_correct is True
    assert result.table_selection_correct is True
    assert result.metric_selection_correct is True
    assert result.filter_selection_correct is True
    assert result.passed is True


def test_clarification_case_passes():
    case = GoldenTextToSQLCase(
        case_id="clarification_case",

        question=(
            "统计本期贷款余额"
        ),

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
            "当前存在科技贷款和绿色贷款"
            "两个可选业务主题。"
        ),
    )

    evaluator = TextToSQLEvaluator()

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert (
        result.actual_behavior
        is ActualAgentBehavior.CLARIFY
    )

    assert result.behavior_correct is True
    assert result.table_selection_correct is None
    assert result.metric_selection_correct is None
    assert result.passed is True


def test_unnecessary_clarification_fails():
    case = GoldenTextToSQLCase(
        case_id=(
            "unnecessary_clarification"
        ),

        question=(
            "统计本期绿色贷款余额"
        ),

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
            "请确认需要哪种贷款。"
        ),
    )

    evaluator = TextToSQLEvaluator()

    result = evaluator.evaluate(
        case=case,
        actual=actual,
    )

    assert (
        result.actual_behavior
        is ActualAgentBehavior.CLARIFY
    )

    assert result.behavior_correct is False
    assert result.passed is False


def test_summary_does_not_penalize_clarification_case():
    evaluator = TextToSQLEvaluator()

    answer_case = GoldenTextToSQLCase(
        case_id="answer",

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

        expected_trusted_sql=True,
    )

    answer_actual = TextToSQLResult(
        question=answer_case.question,

        query_plan=QueryPlan(
            tables=(
                "dwd_hd_201_cldwdk",
            ),

            dimensions=(),
            metrics=(
                "green_loan_balance",
            ),
            filters=(),
            group_by=(),
        ),

        generated_sql=(
            "SELECT SUM(loan_bal_rmb) "
            "FROM dwd_hd_201_cldwdk"
        ),

        trusted_sql=(
            "SELECT SUM(loan_bal_rmb) "
            "FROM dwd_hd_201_cldwdk"
        ),

        success=True,

        validation_status="no_issue",
    )

    clarify_case = GoldenTextToSQLCase(
        case_id="clarify",

        question="统计本期贷款余额",

        expected_behavior=(
            ExpectedAgentBehavior.CLARIFY
        ),

        expected_trusted_sql=False,
    )

    clarify_actual = TextToSQLClarification(
        question=clarify_case.question,

        clarification_question=(
            "请确认科技贷款还是绿色贷款。"
        ),
    )

    results = (
        evaluator.evaluate(
            case=answer_case,
            actual=answer_actual,
        ),

        evaluator.evaluate(
            case=clarify_case,
            actual=clarify_actual,
        ),
    )

    summary = evaluator.summarize(
        results
    )

    assert summary.total_cases == 2
    assert summary.answer_cases == 1
    assert summary.clarification_cases == 1

    assert summary.behavior_accuracy == 1.0

    # CLARIFY Case的None不会进入分母。
    assert (
        summary.table_selection_accuracy
        == 1.0
    )

    assert (
        summary.metric_selection_accuracy
        == 1.0
    )