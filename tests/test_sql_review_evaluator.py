from sql_pilot_engine.evaluation.sql_review_cases import (
    SQLReviewGoldenCase,
)
from sql_pilot_engine.evaluation.sql_review_evaluator import (
    SQLReviewEvaluator,
)
from sql_pilot_engine.schemas.sql_review import (
    SQLReviewIssue,
    SQLReviewResult,
)

def make_result(
    *,
    success: bool,
    status: str,
    trusted_sql: str | None,
    issues=(),
    fix_applied: bool = False,
) -> SQLReviewResult:

    return SQLReviewResult(
        trace_id="trace-1",
        original_sql="SELECT 1",
        reviewed_sql="SELECT 1",
        trusted_sql=trusted_sql,
        success=success,
        review_status=status,
        risk_level="low",
        issues=tuple(
            issues
        ),
        fix_applied=fix_applied,
        route_history=(
            "explain",
            "review",
        ),
        error_message=None,
    )


def test_evaluator_passes_normal_case():

    case = SQLReviewGoldenCase(
        case_id="normal",
        description="normal",
        sql="SELECT 1",
        expected_success=True,
        expect_trusted_sql=True,
    )

    result = make_result(
        success=True,
        status="no_issue",
        trusted_sql="SELECT 1",
    )

    evaluation = (
        SQLReviewEvaluator()
        .evaluate(
            case=case,
            result=result,
        )
    )

    assert evaluation.passed is True
    assert evaluation.failures == ()


def test_evaluator_detects_missing_trusted_sql():

    case = SQLReviewGoldenCase(
        case_id="normal",
        description="normal",
        sql="SELECT 1",
        expected_success=True,
        expect_trusted_sql=True,
    )

    result = make_result(
        success=True,
        status="no_issue",
        trusted_sql=None,
    )

    evaluation = (
        SQLReviewEvaluator()
        .evaluate(
            case=case,
            result=result,
        )
    )

    assert evaluation.passed is False


def test_evaluator_checks_rule_id():

    case = SQLReviewGoldenCase(
        case_id="missing_table",
        description="missing table",
        sql="SELECT * FROM x",
        expected_success=False,
        expect_trusted_sql=False,
        expected_rule_ids=(
            "TABLE_NOT_FOUND",
        ),
    )

    issue = SQLReviewIssue(
        rule_id="TABLE_NOT_FOUND",
        severity="high",
        message="table missing",
        suggestion=None,
        action="block",
        blocking=True,
        auto_fixable=False,
    )

    result = make_result(
        success=False,
        status="blocked",
        trusted_sql=None,
        issues=(
            issue,
        ),
    )

    evaluation = (
        SQLReviewEvaluator()
        .evaluate(
            case=case,
            result=result,
        )
    )

    assert evaluation.passed is True


def test_business_block_is_not_system_failure():

    case = SQLReviewGoldenCase(
        case_id="drop",
        description="drop",
        sql="DROP TABLE x",
        expected_success=False,
        expect_trusted_sql=False,
    )

    result = make_result(
        success=False,
        status="blocked",
        trusted_sql=None,
    )

    evaluation = (
        SQLReviewEvaluator()
        .evaluate(
            case=case,
            result=result,
        )
    )

    assert evaluation.passed is True