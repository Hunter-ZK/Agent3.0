from types import SimpleNamespace

from sql_pilot_engine.evaluation.models import (
    GoldenTextToSQLCase,
)
from sql_pilot_engine.evaluation.runner import (
    TextToSQLEvaluationRunner,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
)


class FakeTextToSQLService:
    def generate(
        self,
        request,
    ):
        return SimpleNamespace(
            question=request.question,

            query_plan=SimpleNamespace(
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
            ),

            success=True,

            trusted_sql=(
                "SELECT user_id, "
                "SUM(order_amount) "
                "FROM dwd_order_detail "
                "GROUP BY user_id"
            ),

            validation_status="no_issue",
        )


class BrokenTextToSQLService:
    def generate(
        self,
        request,
    ):
        raise RuntimeError(
            "LLM unavailable"
        )


def build_case() -> GoldenTextToSQLCase:
    return GoldenTextToSQLCase(
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


def test_runner_executes_case():
    runner = TextToSQLEvaluationRunner(
        service=FakeTextToSQLService(),
        evaluator=TextToSQLEvaluator(),
    )

    report = runner.run(
        [build_case()]
    )

    assert (
        report.summary.total_cases
        == 1
    )

    assert (
        report.summary.pass_rate
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


def test_runner_keeps_error_case():
    runner = TextToSQLEvaluationRunner(
        service=BrokenTextToSQLService(),
        evaluator=TextToSQLEvaluator(),
    )

    report = runner.run(
        [build_case()]
    )

    result = report.results[0]

    assert result.passed is False

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