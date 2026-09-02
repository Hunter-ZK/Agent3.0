from __future__ import annotations

from sql_pilot_engine.evaluation.text_to_sql.evaluator import (
    evaluate_case,
)

from sql_pilot_engine.evaluation.text_to_sql.models import (
    EvaluationFailureType,
    TextToSQLEvalCase,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLResult,
    TextToSQLValidationIssue,
)


class FakeService:

    def __init__(
        self,
        response,
    ) -> None:
        self.response = response

    def generate(
        self,
        request,
    ):
        _ = request
        return self.response


def _plan() -> QueryPlan:

    return QueryPlan(
        tables=(
            "ods_hd_100_cldkxx",
        ),

        dimensions=(),

        metrics=(
            "tech_loan_balance",
        ),

        filters=(
            "dt = '202607'",
        ),

        group_by=(),
    )


def _case() -> TextToSQLEvalCase:

    return TextToSQLEvalCase(
        case_id="test_case",

        question=(
            "统计2026年7月科技贷款余额"
        ),

        expected_initial="result",

        expected_tables=(
            "ods_hd_100_cldkxx",
        ),

        expected_metrics=(
            "tech_loan_balance",
        ),

        required_filter_terms=(
            "202607",
        ),
    )


def _response(
    *,
    semantic_status: str = "pass",
    success: bool = True,
    trusted_sql: str | None = (
        "SELECT SUM(loan_bal_rmb) "
        "FROM ods_hd_100_cldkxx "
        "WHERE dt = '202607'"
    ),
    validation_status: str = (
        "no_issue"
    ),
    validation_issues=(),
):

    sql = (
        "SELECT SUM(loan_bal_rmb) "
        "FROM ods_hd_100_cldkxx "
        "WHERE dt = '202607'"
    )

    return TextToSQLResult(
        question=(
            "统计2026年7月科技贷款余额"
        ),

        query_plan=_plan(),

        generated_sql=sql,

        trusted_sql=trusted_sql,

        success=success,

        validation_status=(
            validation_status
        ),

        validation_error_message=None,

        validation_issues=(
            validation_issues
        ),

        semantic_validation_status=(
            semantic_status
        ),

        semantic_missing_requirements=(),

        semantic_issues=(),
    )


def test_evaluation_scores_all_six_layers():

    result = evaluate_case(
        service=FakeService(
            _response()
        ),

        case=_case(),

        run_index=1,
    )

    assert (
        result.planning_pass
        is True
    )

    assert (
        result.schema_link_pass
        is True
    )

    assert (
        result.generation_pass
        is True
    )

    assert (
        result.gate_pass
        is True
    )

    assert (
        result.semantic_pass
        is True
    )

    assert (
        result.final_pass
        is True
    )

    assert (
        result.failure_type
        is None
    )


def test_evaluation_preserves_evidence_rule_hits():

    issue = (
        TextToSQLValidationIssue(
            rule_id=(
                "METRIC_AGGREGATION"
            ),

            source="rule",

            severity="high",

            action="advisory",

            category="semantic",

            message=(
                "test advisory"
            ),

            evidence=(
                "test evidence"
            ),
        )
    )

    result = evaluate_case(
        service=FakeService(
            _response(
                validation_status=(
                    "trusted_with_advisories"
                ),

                validation_issues=(
                    issue,
                ),
            )
        ),

        case=_case(),

        run_index=1,
    )

    assert (
        result.final_pass
        is True
    )

    assert (
        result.evidence_rule_hits
        == (
            "METRIC_AGGREGATION",
        )
    )


def test_gate_false_negative_is_redline_failure():

    result = evaluate_case(
        service=FakeService(
            _response(
                semantic_status="fail",

                success=False,

                trusted_sql=None,

                validation_status=(
                    "no_issue"
                ),
            )
        ),

        case=_case(),

        run_index=1,
    )

    assert (
        result.gate_pass
        is True
    )

    assert (
        result.semantic_pass
        is False
    )

    assert (
        result.final_pass
        is False
    )

    assert (
        result.failure_type
        is (
            EvaluationFailureType
            .GATE_FALSE_NEGATIVE
        )
    )


def test_generation_failure_is_classified():

    response = _response()

    response = (
        TextToSQLResult(
            question=(
                response.question
            ),

            query_plan=(
                response.query_plan
            ),

            generated_sql="",

            trusted_sql=None,

            success=False,

            validation_status=(
                "not_run"
            ),

            validation_error_message=None,

            validation_issues=(),

            semantic_validation_status=None,

            semantic_missing_requirements=(),

            semantic_issues=(),
        )
    )

    result = evaluate_case(
        service=FakeService(
            response
        ),

        case=_case(),

        run_index=1,
    )

    assert (
        result.generation_pass
        is False
    )

    assert (
        result.failure_type
        is (
            EvaluationFailureType
            .GENERATION_ERROR
        )
    )


def test_review_failure_is_system_error():

    result = evaluate_case(
        service=FakeService(
            _response(
                semantic_status=None,

                success=False,

                trusted_sql=None,

                validation_status=(
                    "review_failed"
                ),
            )
        ),

        case=_case(),

        run_index=1,
    )

    assert (
        result.system_error
        is True
    )

    assert (
        result.failure_type
        is (
            EvaluationFailureType
            .SYSTEM_ERROR
        )
    )