from sql_review_agent.agents.sql_critic_agent import SQLCriticAgent
from sql_review_agent.schemas.responses import SQLFixResponse, SQLReviewResponse


def make_review_response(issue_count: int = 1) -> SQLReviewResponse:
    return SQLReviewResponse(
        success=True,
        task_type="review",
        file_path="test.sql",
        trace_id="trace-critic",
        risk_level="medium",
        issue_count=issue_count,
        issues=[{"id": "ISSUE_001"}] if issue_count > 0 else [],
    )

def make_re_review_response(
    issue_count: int = 0,
    success: bool = True,
) -> SQLReviewResponse:
    return SQLReviewResponse(
        success=success,
        task_type="review",
        file_path="test.sql",
        trace_id="trace-critic",
        risk_level="low" if issue_count == 0 else "medium",
        issue_count=issue_count,
        issues=(
            [{"id": "REMAINING_ISSUE"}]
            if issue_count > 0
            else []
        ),
        error_message=None if success else "re-review failed",
    )

def make_fix_response(
    success: bool = True,
    fixed_sql: str | None = "select 1 limit 100",
    applied_fixes: list[str] | None = None,
    manual_notes: list[str] | None = None,
) -> SQLFixResponse:
    return SQLFixResponse(
        success=success,
        task_type="fix",
        file_path="test.sql",
        trace_id="trace-critic",
        risk_level="medium",
        issue_count=1,
        issues=[],
        fixed_sql=fixed_sql,
        applied_fixes=applied_fixes if applied_fixes is not None else ["add_limit"],
        manual_notes=manual_notes if manual_notes is not None else [],
        fix_source="auto",
        error_message=None if success else "fix failed",
    )


def test_critic_should_pass_when_fix_is_valid():
    critic = SQLCriticAgent()

    response = critic.critique(
        review_response=make_review_response(issue_count=1),
        fix_response=make_fix_response(),
        trace_id="trace-critic",
    )

    assert response.success is True
    assert response.passed is True
    assert response.status == "passed"
    assert response.need_human_confirm is False
    assert response.trace_id == "trace-critic"


def test_critic_should_fail_when_fix_failed():
    critic = SQLCriticAgent()

    response = critic.critique(
        review_response=make_review_response(issue_count=1),
        fix_response=make_fix_response(success=False),
        trace_id="trace-critic",
    )

    assert response.success is True
    assert response.passed is False
    assert response.status == "fix_failed"
    assert response.need_human_confirm is True


def test_critic_should_fail_when_fixed_sql_missing():
    critic = SQLCriticAgent()

    response = critic.critique(
        review_response=make_review_response(issue_count=1),
        fix_response=make_fix_response(fixed_sql=None),
        re_review_response=make_re_review_response(issue_count=0),
        trace_id="trace-critic",
    )

    assert response.passed is False
    assert response.status == "no_fixed_sql"
    assert response.need_human_confirm is True


def test_critic_should_fail_when_applied_fixes_missing():
    critic = SQLCriticAgent()

    response = critic.critique(
        review_response=make_review_response(issue_count=1),
        fix_response=make_fix_response(applied_fixes=[]),
        re_review_response=make_re_review_response(issue_count=0),
        trace_id="trace-critic",
    )

    assert response.passed is False
    assert response.status == "no_applied_fixes"
    assert response.need_human_confirm is True


def test_critic_should_require_human_confirm_when_manual_notes_exist():
    critic = SQLCriticAgent()

    response = critic.critique(
        review_response=make_review_response(issue_count=1),
        fix_response=make_fix_response(
            manual_notes=["业务口径不确定，需要人工确认"]
        ),
        re_review_response=make_re_review_response(issue_count=0),
        trace_id="trace-critic",
    )

    assert response.passed is False
    assert response.status == "need_human_confirm"
    assert response.need_human_confirm is True
    assert response.warnings