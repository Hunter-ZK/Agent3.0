import pytest

from sql_pilot_engine.core.enums import (
    IssueAction,
    IssueSource,
    Severity,
)
from sql_pilot_engine.core.execution_context import (
    ReviewExecutionContext,
)
from sql_pilot_engine.core.models import (
    FixedSqlResult,
    Issue,
    ReviewResult,
)
from sql_pilot_engine.schemas.responses import (
    SQLCriticResponse,
    SQLFixResponse,
    SQLReviewResponse,
)
from sql_pilot_engine.services.fix_service import (
    FixService,
)
from sql_pilot_engine.workflow.review_routing import (
    ReviewRoute,
    decide_review_route,
)
from sql_pilot_engine.workflow.sql_agent_workflow import (
    SQLAgentWorkflow,
)


def build_issue(
    *,
    action: IssueAction,
    auto_fixable: bool = False,
    blocking: bool = False,
) -> Issue:
    return Issue(
        rule_id="TEST_RULE",
        title="Test issue",
        severity=Severity.MEDIUM,
        message="Test message",
        suggestion="Test suggestion",
        evidence="test",
        category="test",
        source=IssueSource.RULE,
        action=action,
        auto_fixable=auto_fixable,
        blocking=blocking,
    )


def build_review_response(
    sql: str,
    issues: list[Issue],
) -> SQLReviewResponse:
    result = ReviewResult(
        file_path="<memory>",
        reviewed_sql=sql,
        risk_level=(
            Severity.MEDIUM
            if issues
            else Severity.LOW
        ),
        issue_count=len(issues),
        issues=issues,
    )

    return SQLReviewResponse.from_review_result(
        result
    )


def test_auto_fix_requires_all_issues_to_be_auto_fixable():
    response = build_review_response(
        sql="SELECT * FROM t",
        issues=[
            build_issue(
                action=IssueAction.AUTO_FIX,
                auto_fixable=True,
            )
        ],
    )

    decision = decide_review_route(
        response
    )

    assert decision.route == ReviewRoute.AUTO_FIX


def test_blocking_issue_has_highest_priority():
    response = build_review_response(
        sql="DROP TABLE t",
        issues=[
            build_issue(
                action=IssueAction.AUTO_FIX,
                auto_fixable=True,
            ),
            build_issue(
                action=IssueAction.BLOCK,
                blocking=True,
            ),
        ],
    )

    decision = decide_review_route(
        response
    )

    assert decision.route == ReviewRoute.BLOCK


class FakeWorkflowEngine:
    explain_available = False

    def __init__(self) -> None:
        self.review_calls = 0
        self.prior_review = None

    def review(self, request):
        self.review_calls += 1

        if self.review_calls == 1:
            return build_review_response(
                sql=request.sql,
                issues=[
                    build_issue(
                        action=(
                            IssueAction.AUTO_FIX
                        ),
                        auto_fixable=True,
                    )
                ],
            )

        return build_review_response(
            sql=request.sql,
            issues=[],
        )

    def fix(
        self,
        request,
        *,
        prior_review=None,
    ):
        self.prior_review = prior_review

        return SQLFixResponse(
            success=True,
            task_type="fix",
            file_path=request.file_path,
            risk_level="medium",
            issue_count=1,
            issues=[],
            fixed_sql="SELECT id FROM t",
            applied_fixes=["TEST_RULE"],
        )

    def critique(
        self,
        *,
        review_response,
        fix_response,
        re_review_response,
        trace_id=None,
    ):
        return SQLCriticResponse(
            success=True,
            passed=True,
            trace_id=trace_id,
            status="passed",
        )


def test_workflow_skips_explain_and_reuses_review():
    engine = FakeWorkflowEngine()

    workflow = SQLAgentWorkflow(
        engine=engine,
        max_retries=0,
    )

    result = workflow.run(
        "SELECT * FROM t"
    )

    assert result.success is True
    assert result.final_status == "fix_verified"
    assert result.route_history[0] == (
        "explain_skipped"
    )
    assert engine.review_calls == 2
    assert engine.prior_review is (
        result.review_response
    )


class RecordingReviewService:
    def __init__(self) -> None:
        self.calls = 0

    def review(self, context):
        self.calls += 1
        raise AssertionError(
            "Review should have been reused."
        )


class StubFixService(FixService):
    def _generate_fixed_sql(
        self,
        *,
        context,
        review_result,
        analysis_context_text,
        metadata_context_text,
    ):
        return FixedSqlResult(
            fixed_sql=context.sql,
            applied_fixes=[],
        )


def test_fix_service_reuses_matching_review_result():
    review_service = RecordingReviewService()

    service = StubFixService(
        review_service=review_service
    )

    prior_result = ReviewResult(
        file_path="<memory>",
        reviewed_sql="SELECT 1",
        risk_level=Severity.LOW,
        issue_count=0,
        issues=[],
    )

    context = ReviewExecutionContext(
        sql="SELECT 1",
        fix_sql=True,
    )

    result = service.fix(
        context,
        review_result=prior_result,
    )

    assert result.reviewed_sql == "SELECT 1"
    assert review_service.calls == 0


def test_fix_service_rejects_mismatched_review():
    service = StubFixService(
        review_service=(
            RecordingReviewService()
        )
    )

    prior_result = ReviewResult(
        file_path="<memory>",
        reviewed_sql="SELECT 2",
        risk_level=Severity.LOW,
        issue_count=0,
        issues=[],
    )

    context = ReviewExecutionContext(
        sql="SELECT 1",
        fix_sql=True,
    )

    with pytest.raises(
        ValueError,
        match="does not belong",
    ):
        service.fix(
            context,
            review_result=prior_result,
        )