from __future__ import annotations

from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    ExpectedAgentBehavior,
    GoldenTextToSQLCase,
)
from sql_pilot_engine.evaluation.runner import (
    TextToSQLEvaluationRunner,
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


class FakeTextToSQLService:
    """固定返回一个正确ANSWER结果。"""

    def generate(
        self,
        request,
    ) -> TextToSQLResult:
        return TextToSQLResult(
            question=request.question,

            query_plan=QueryPlan(
                tables=(
                    "dwd_order_detail",
                ),

                dimensions=(
                    "user_id",
                ),

                metrics=(
                    "total_order_amount",
                ),

                filters=(),

                group_by=(
                    "user_id",
                ),
            ),

            generated_sql=(
                "SELECT user_id, "
                "SUM(order_amount) "
                "FROM dwd_order_detail "
                "GROUP BY user_id"
            ),

            trusted_sql=(
                "SELECT user_id, "
                "SUM(order_amount) "
                "FROM dwd_order_detail "
                "GROUP BY user_id"
            ),

            success=True,

            validation_status="no_issue",

            semantic_validation_status=(
                "pass"
            ),
        )


class ClarificationTextToSQLService:
    """固定返回一个Clarification结果。"""

    def generate(
        self,
        request,
    ) -> TextToSQLClarification:
        return TextToSQLClarification(
            question=request.question,

            clarification_question=(
                "请确认科技贷款还是绿色贷款。"
            ),

            missing_context=(
                "贷款业务主题",
            ),

            reason=(
                "当前问题存在多个业务主题。"
            ),
        )


class BrokenTextToSQLService:
    """模拟底层运行异常。"""

    def generate(
        self,
        request,
    ):
        raise RuntimeError(
            "LLM unavailable"
        )


def build_answer_case() -> (
    GoldenTextToSQLCase
):
    return GoldenTextToSQLCase(
        case_id="case-001",

        question=(
            "统计每个用户订单总金额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
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

        expected_filters=(),

        expected_group_by=(
            "user_id",
        ),

        expected_trusted_sql=True,
    )


def build_clarify_case() -> (
    GoldenTextToSQLCase
):
    return GoldenTextToSQLCase(
        case_id="case-clarify",

        question="统计本期贷款余额",

        expected_behavior=(
            ExpectedAgentBehavior.CLARIFY
        ),

        expected_trusted_sql=False,
    )


def test_runner_executes_answer_case():
    runner = TextToSQLEvaluationRunner(
        service=FakeTextToSQLService(),
        evaluator=TextToSQLEvaluator(),
    )

    report = runner.run(
        [build_answer_case()]
    )

    assert (
        report.summary.total_cases
        == 1
    )

    assert (
        report.summary.answer_cases
        == 1
    )

    assert (
        report.summary.pass_rate
        == 1.0
    )

    assert (
        report.summary.behavior_accuracy
        == 1.0
    )

    assert (
        report.summary.error_rate
        == 0.0
    )

    assert (
        report.results[0].passed
        is True
    )

    assert (
        report.results[0].actual_behavior
        is ActualAgentBehavior.ANSWER
    )


def test_runner_executes_clarification_case():
    runner = TextToSQLEvaluationRunner(
        service=(
            ClarificationTextToSQLService()
        ),

        evaluator=TextToSQLEvaluator(),
    )

    report = runner.run(
        [build_clarify_case()]
    )

    result = report.results[0]

    assert result.passed is True

    assert (
        result.actual_behavior
        is ActualAgentBehavior.CLARIFY
    )

    assert (
        result.behavior_correct
        is True
    )

    assert (
        report.summary
        .clarification_cases
        == 1
    )

    assert (
        report.summary
        .behavior_accuracy
        == 1.0
    )


def test_runner_keeps_error_case():
    runner = TextToSQLEvaluationRunner(
        service=BrokenTextToSQLService(),
        evaluator=TextToSQLEvaluator(),
    )

    report = runner.run(
        [build_answer_case()]
    )

    result = report.results[0]

    assert result.passed is False

    assert (
        result.actual_behavior
        is ActualAgentBehavior.ERROR
    )

    assert (
        result.behavior_correct
        is False
    )

    assert (
        result.pipeline_success
        is False
    )

    assert (
        result.validation_status
        == "evaluation_error"
    )

    assert (
        result.error_message
        == (
            "RuntimeError: "
            "LLM unavailable"
        )
    )

    assert (
        report.summary.error_rate
        == 1.0
    )

    assert (
        report.summary.behavior_accuracy
        == 0.0
    )