from __future__ import annotations

from types import SimpleNamespace

from sql_pilot_engine.evaluation.models import (
    ExpectedAgentBehavior,
    GoldenTextToSQLCase,
)
from sql_pilot_engine.evaluation.runtime_parity import (
    RuntimeParityRunner,
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


QUESTION = (
    "统计本期绿色贷款余额"
)


def build_case() -> GoldenTextToSQLCase:
    return GoldenTextToSQLCase(
        case_id="green_balance",

        question=QUESTION,

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=("dt",),

        expected_metrics=(
            "green_loan_balance",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=("dt",),

        expected_trusted_sql=True,
    )


def build_result(
    *,
    table: str = (
        "dwd_hd_201_cldwdk"
    ),
) -> TextToSQLResult:

    return TextToSQLResult(
        question=QUESTION,

        query_plan=QueryPlan(
            tables=(table,),

            dimensions=("dt",),

            metrics=(
                "green_loan_balance",
            ),

            filters=(
                "dt = "
                "'${p_month_yyyymm}'",
            ),

            group_by=("dt",),
        ),

        generated_sql="SELECT 1",

        trusted_sql="SELECT 1",

        success=True,

        validation_status="no_issue",

        semantic_validation_status=(
            "pass"
        ),
    )


class FakePythonService:

    def __init__(
        self,
        response,
    ) -> None:
        self.response = response

    def generate(
        self,
        request,
    ):
        return self.response


class FakeAnswerGraph:

    def __init__(
        self,
        *,
        table: str = (
            "dwd_hd_201_cldwdk"
        ),
    ) -> None:
        self.table = table

    def start(
        self,
        **kwargs,
    ):
        return {
            "query_plan": QueryPlan(
                tables=(
                    self.table,
                ),

                dimensions=("dt",),

                metrics=(
                    "green_loan_balance",
                ),

                filters=(
                    "dt = "
                    "'${p_month_yyyymm}'",
                ),

                group_by=("dt",),
            ),

            "generated_sql": (
                "SELECT 1"
            ),

            "trusted_sql": (
                "SELECT 1"
            ),

            "success": True,

            "validation_status": (
                "no_issue"
            ),

            "semantic_validation_status": (
                "pass"
            ),
        }


class FakeClarifyGraph:

    def start(
        self,
        **kwargs,
    ):
        return {
            "__interrupt__": (
                SimpleNamespace(
                    value={
                        "question": (
                            "请确认贷款业务主题。"
                        ),

                        "missing_context": (
                            "贷款业务主题",
                        ),

                        "reason": (
                            "业务主题存在歧义"
                        ),
                    }
                ),
            )
        }


def build_runner(
    *,
    python_response,
    graph,
) -> RuntimeParityRunner:

    return RuntimeParityRunner(
        python_service=(
            FakePythonService(
                python_response
            )
        ),

        langgraph=graph,

        evaluator=(
            TextToSQLEvaluator()
        ),
    )


def test_same_answer_has_parity():

    runner = build_runner(
        python_response=(
            build_result()
        ),

        graph=(
            FakeAnswerGraph()
        ),
    )

    report = runner.run(
        (build_case(),)
    )

    result = report.results[0]

    assert (
        result.parity_passed
        is True
    )

    assert result.behavior_equal
    assert result.tables_equal
    assert result.metrics_equal

    assert (
        report.parity_rate
        == 1.0
    )


def test_plan_change_breaks_parity():

    runner = build_runner(
        python_response=(
            build_result()
        ),

        graph=FakeAnswerGraph(
            table=(
                "dwd_hd_101_cldwdk"
            )
        ),
    )

    result = runner.run(
        (build_case(),)
    ).results[0]

    assert (
        result.parity_passed
        is False
    )

    assert (
        result.behavior_equal
        is True
    )

    assert (
        result.tables_equal
        is False
    )


def test_answer_vs_clarify_breaks_parity():

    runner = build_runner(
        python_response=(
            build_result()
        ),

        graph=(
            FakeClarifyGraph()
        ),
    )

    result = runner.run(
        (build_case(),)
    ).results[0]

    assert (
        result.parity_passed
        is False
    )

    assert (
        result.behavior_equal
        is False
    )


def test_two_clarifications_have_behavior_parity():

    clarify_case = (
        GoldenTextToSQLCase(
            case_id="ambiguous",

            question=(
                "统计本期贷款余额"
            ),

            expected_behavior=(
                ExpectedAgentBehavior
                .CLARIFY
            ),

            expected_trusted_sql=False,
        )
    )

    python_response = (
        TextToSQLClarification(
            question=(
                "统计本期贷款余额"
            ),

            clarification_question=(
                "请确认科技贷款"
                "还是绿色贷款。"
            ),
        )
    )

    runner = build_runner(
        python_response=(
            python_response
        ),

        graph=(
            FakeClarifyGraph()
        ),
    )

    # FakeGraph payload中的原问题
    # 不参与Response.question生成，
    # Runner会使用Golden Request。
    report = runner.run(
        (clarify_case,)
    )

    result = report.results[0]

    assert (
        result.parity_passed
        is True
    )

    assert (
        result.behavior_equal
        is True
    )