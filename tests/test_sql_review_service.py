from types import (
    SimpleNamespace,
)

from sql_pilot_engine.schemas.sql_review import (
    SQLReviewInput,
)
from sql_pilot_engine.capabilities.sql_review import (
    SQLReviewService,
)


class FakeWorkflow:

    def __init__(
        self,
        *,
        result=None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

    def run(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
    ):
        _ = sql
        _ = dialect

        if self.error is not None:
            raise self.error

        return self.result


def make_review_response(
    *,
    sql: str,
    risk_level: str = "low",
    issues=None,
):
    return SimpleNamespace(
        success=True,
        risk_level=risk_level,
        issues=issues or [],
        raw_result=SimpleNamespace(
            reviewed_sql=sql,
        ),
    )


def make_result(
    *,
    success: bool,
    final_status: str,
    sql: str,
    issues=None,
    fix_response=None,
    re_review_response=None,
    error_message=None,
    trusted_sql: str | None = None,
    final_sql: str | None = None,
):
    return SimpleNamespace(
        success=success,
        final_status=final_status,
        review_response=(
            make_review_response(
                sql=sql,
                issues=issues,
            )
        ),
        fix_response=fix_response,
        re_review_response=(
            re_review_response
        ),
        critic_response=None,
        route_history=[
            "explain",
            "review",
        ],
        error_message=error_message,
        trusted_sql=trusted_sql,
        final_sql=(
            final_sql
            if final_sql is not None
            else trusted_sql
        ),
    )


def test_normal_sql_returns_trusted_sql():
    sql = """
    SELECT user_id
    FROM user_table
    """.strip()

    workflow = FakeWorkflow(
        result=make_result(
            success=True,
            final_status="no_issue",
            sql=sql,
        )
    )

    service = SQLReviewService(
        workflow=workflow
    )

    result = service.review(
        SQLReviewInput(
            sql=sql
        )
    )

    assert result.success is True

    assert (
        result.review_status
        == "no_issue"
    )

    assert (
        result.trusted_sql
        == sql
    )

    assert result.fix_applied is False


def test_blocked_sql_has_no_trusted_sql():
    sql = (
        "DROP TABLE user_table"
    )

    issue = {
        "rule_id": "DANGEROUS_DROP",
        "severity": "high",
        "message": (
            "DROP operation is blocked."
        ),
        "suggestion": None,
        "blocking": True,
        "auto_fixable": False,
    }

    workflow = FakeWorkflow(
        result=make_result(
            success=False,
            final_status="blocked",
            sql=sql,
            issues=[
                issue
            ],
        )
    )

    service = SQLReviewService(
        workflow=workflow
    )

    result = service.review(
        SQLReviewInput(
            sql=sql
        )
    )

    assert result.success is False

    assert (
        result.review_status
        == "blocked"
    )

    assert result.trusted_sql is None

    assert len(result.issues) == 1

    assert (
        result.issues[0].blocking
        is True
    )


def test_metadata_required_is_not_review_failed():
    sql = """
    SELECT amount
    FROM business_table
    """.strip()

    issue = {
        "rule_id": (
            "METADATA_LOOKUP_FAILED"
        ),
        "severity": "medium",
        "message": (
            "Metadata is unavailable."
        ),
        "suggestion": (
            "Check metadata source."
        ),
        "blocking": False,
        "auto_fixable": False,
    }

    workflow = FakeWorkflow(
        result=make_result(
            success=False,
            final_status=(
                "metadata_required"
            ),
            sql=sql,
            issues=[
                issue
            ],
            error_message=(
                "Metadata context "
                "is required."
            ),
        )
    )

    service = SQLReviewService(
        workflow=workflow
    )

    result = service.review(
        SQLReviewInput(
            sql=sql
        )
    )

    assert result.success is False

    assert (
        result.review_status
        == "metadata_required"
    )

    assert (
        result.review_status
        != "review_failed"
    )

    assert result.trusted_sql is None


def test_fixed_sql_becomes_trusted_sql():
    original_sql = """
    SELECT *
    FROM user_table
    """.strip()

    fixed_sql = """
    SELECT user_id
    FROM user_table
    """.strip()

    fix_response = (
        SimpleNamespace(
            success=True,
            fixed_sql=fixed_sql,
            raw_result=None,
        )
    )

    re_review_response = (
        make_review_response(
            sql=fixed_sql,
            risk_level="low",
        )
    )

    workflow = FakeWorkflow(
        result=make_result(
            success=True,
            final_status=(
                "fix_verified"
            ),
            sql=original_sql,
            fix_response=(
                fix_response
            ),
            re_review_response=(
                re_review_response
            ),
        )
    )

    service = SQLReviewService(
        workflow=workflow
    )

    result = service.review(
        SQLReviewInput(
            sql=original_sql
        )
    )

    assert result.success is True

    assert (
        result.review_status
        == "fixed"
    )

    assert (
        result.fix_applied
        is True
    )

    assert (
        result.trusted_sql
        == fixed_sql
    )


def test_internal_error_maps_to_review_failed():
    service = SQLReviewService(
        workflow=FakeWorkflow(
            error=RuntimeError(
                "unexpected failure"
            )
        )
    )

    result = service.review(
        SQLReviewInput(
            sql=(
                "SELECT 1"
            )
        )
    )

    assert result.success is False

    assert (
        result.review_status
        == "review_failed"
    )

    assert result.trusted_sql is None

    assert (
        result.error_message
        == "unexpected failure"
    )


def test_issue_is_projected_to_public_contract():
    sql = (
        "SELECT * FROM user_table"
    )

    issue = {
        "rule_id": "SELECT_STAR",
        "severity": "medium",
        "message": (
            "Avoid SELECT *."
        ),
        "suggestion": (
            "Select explicit columns."
        ),
        "blocking": False,
        "auto_fixable": True,
    }

    workflow = FakeWorkflow(
        result=make_result(
            success=False,
            final_status="blocked",
            sql=sql,
            issues=[
                issue
            ],
        )
    )

    service = SQLReviewService(
        workflow=workflow
    )

    result = service.review(
        SQLReviewInput(
            sql=sql
        )
    )

    public_issue = (
        result.issues[0]
    )

    assert (
        public_issue.rule_id
        == "SELECT_STAR"
    )

    assert (
        public_issue.severity
        == "medium"
    )

    assert (
        public_issue.auto_fixable
        is True
    )