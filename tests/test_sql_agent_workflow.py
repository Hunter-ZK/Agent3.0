from sql_review_agent.schemas.responses import SQLExplainResponse,SQLFixResponse,SQLReviewResponse
from sql_review_agent.workflow.sql_agent_workflow import SQLAgentWorkflow
from sql_review_agent.agents.sql_critic_agent import SQLCriticAgent

class FakeExplainAgent:
    def __init__(
        self,
        route_signals: dict | None = None,
        success: bool = True,
    ):
        self.route_signals = route_signals or {
            "need_review": True,
            "can_auto_fix": True,
            "need_human_confirm": False,
            "need_metadata": False,
            "need_rag": False,
        }
        self.success = success

    def explain(self, request, trace_id=None):
        return SQLExplainResponse(
            success=self.success,
            file_path=request.file_path,
            trace_id=trace_id,
            route_signals=self.route_signals,
            error_message=None if self.success else "explain failed",
        )
    def review(self, request):
        if "limit 100" in request.sql.lower():
            return SQLReviewResponse(
                success=True,
                task_type="review",
                file_path=request.file_path,
                trace_id=request.trace_id,
                risk_level="low",
                issue_count=0,
                issues=[],
            )

        return SQLReviewResponse(
            success=True,
            task_type="review",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="medium",
            issue_count=1,
            issues=[
                {
                    "id": "ISSUE_001",
                    "type": "missing_limit",
                    "message": "缺少 limit",
                }
            ],
        )
    
    def fix(self, request):
        return SQLFixResponse(
            success=True,
            task_type="fix",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="medium",
            issue_count=1,
            issues=[],
            fixed_sql="select 1 limit 100",
            applied_fixes=["add_limit"],
            manual_notes=[],
            fix_source="auto",
        )

class FakeEngineReviewClean:
    def review(self, request):
        return SQLReviewResponse(
            success=True,
            task_type="review",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="low",
            issue_count=0,
            issues=[],
        )

    def fix(self, request):
        raise AssertionError(
            "Fix must not run when review has no issues."
        )


class FakeEngineNoIssue:
    def explain(self, request):
        return SQLExplainResponse(
            success=True,
            file_path=request.file_path,
            trace_id=request.trace_id,
            sql_summary="explain ok",
        )
    
    def review(self, request):
        return SQLReviewResponse(
            success=True,
            task_type="review",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="low",
            issue_count=0,
            issues=[],
        )
    
    def fix(self, request):
        raise AssertionError("fix should not be called when issue_count is 0")
    
def test_workflow_should_stop_when_no_issue():
    workflow = SQLAgentWorkflow(engine=FakeEngineNoIssue(),critic_agent=SQLCriticAgent())

    result = workflow.run(sql = "select 1", file_path="no_issue.sql")

    assert result.success is True
    assert result.final_status == "no_issue"
    assert result.explain_response is not None
    assert result.review_response is not None
    assert result.fix_response is None
    assert result.route_history == ["explain", "review"]

    assert result.explain_response.trace_id == result.trace_id
    assert result.review_response.trace_id == result.trace_id



class FakeEngineFixVerified:
    def explain(self, request):
        return SQLExplainResponse(
            success=True,
            file_path=request.file_path,
            trace_id=request.trace_id,
            sql_summary="explain ok",
        )
    
    def review(self, request):
        if "limit 100" in request.sql.lower():
            return SQLReviewResponse(
                success=True,
                task_type="review",
                file_path=request.file_path,
                trace_id=request.trace_id,
                risk_level="low",
                issue_count=0,
                issues=[],
            )

        return SQLReviewResponse(
            success=True,
            task_type="review",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="medium",
            issue_count=1,
            issues=[
                {
                    "id": "ISSUE_001",
                    "type": "missing_limit",
                    "message": "缺少 limit",
                }
            ],
        )
    
    def fix(self, request):
        return SQLFixResponse(
            success=True,
            task_type="fix",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="medium",
            issue_count=1,
            issues=[],
            fixed_sql="select 1 limit 100",
            applied_fixes=["add_limit"],
            manual_notes=[],
            fix_source="auto",
        )
    

def test_workflow_should_fix_and_verify_when_issue_exists():
    workflow = SQLAgentWorkflow(engine=FakeEngineFixVerified(),critic_agent=SQLCriticAgent())
    result = workflow.run(sql = "select 1", file_path="fix.sql")

    assert result.success is True
    assert result.final_status == "fix_verified"
    assert result.route_history == ["explain", "review", "fix","re_review", "critic"]

    assert result.explain_response.trace_id == result.trace_id
    assert result.review_response.trace_id == result.trace_id
    assert result.fix_response.trace_id == result.trace_id

    assert result.critic_response.passed is True
    assert result.critic_response is not None

    assert result.re_review_response is not None
    assert result.re_review_response.passed is True

    assert result.critic_response.trace_id == result.trace_id


class FakeEngineFixNeedsHuman:
    def explain(self, request):
        return SQLExplainResponse(
            success=True,
            file_path=request.file_path,
            trace_id=request.trace_id,
            sql_summary="explain ok",
        )

    def review(self, request):
        return SQLReviewResponse(
            success=True,
            task_type="review",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="high",
            issue_count=1,
            issues=[
                {
                    "id": "ISSUE_001",
                    "type": "business_logic_uncertain",
                    "message": "业务口径不确定",
                }
            ],
        )

    def fix(self, request):
        return SQLFixResponse(
            success=True,
            task_type="fix",
            file_path=request.file_path,
            trace_id=request.trace_id,
            risk_level="high",
            issue_count=1,
            issues=[],
            fixed_sql=None,
            applied_fixes=[],
            manual_notes=["业务口径不确定，需要人工确认"],
            fix_source="auto",
        )


def test_workflow_should_require_human_confirm_when_fix_not_verified():
    workflow = SQLAgentWorkflow(engine=FakeEngineFixNeedsHuman(),critic_agent=SQLCriticAgent())

    result = workflow.run(sql="select 1", file_path="human.sql")

    assert result.success is False
    assert result.final_status == "need_human_confirm"
    assert result.route_history == ["explain", "review", "fix", "critic"]
    assert result.re_review_response is None
    assert result.critic_response is not None
    assert result.critic_response.passed is False
    assert result.critic_response.need_human_confirm is True




def test_workflow_should_stop_after_explain_when_review_not_needed():
    workflow = SQLAgentWorkflow(
        engine=FakeExplainAgent(
            route_signals={
                "need_review": False,
            }
        ),
        critic_agent=SQLCriticAgent(),
    )

    result = workflow.run(
        sql="select 1",
        file_path="test.sql",
    )

    assert result.success is True
    assert result.final_status == "explained"
    assert result.route_history == ["explain"]
    assert result.review_response is None
    assert result.fix_response is None


def test_workflow_should_stop_when_review_is_clean():
    workflow = SQLAgentWorkflow(
        engine=FakeExplainAgent(),
        critic_agent=SQLCriticAgent(),
    )

    result = workflow.run(
        sql="select 1 limit 100",
        file_path="test.sql",
    )

    assert result.success is True
    assert result.final_status == "review_clean"
    assert result.route_history == [
        "explain",
        "review",
    ]
    assert result.fix_response is None

def test_workflow_should_require_human_when_auto_fix_disabled():
    workflow = SQLAgentWorkflow(
        engine=FakeExplainAgent(
            route_signals={
                "need_review": True,
                "can_auto_fix": False,
                "need_human_confirm": False,
                "need_metadata": False,
                "need_rag": False,
            }
        ),
        critic_agent=SQLCriticAgent(),
    )

    result = workflow.run(
        sql="select 1",
        file_path="test.sql",
    )

    assert result.success is False
    assert result.final_status == "need_human_confirm"
    assert result.route_history == [
        "explain",
        "review",
    ]
    assert result.fix_response is None


def test_workflow_should_stop_when_context_is_required():
    workflow = SQLAgentWorkflow(
        engine=FakeExplainAgent(
            route_signals={
                "need_review": True,
                "can_auto_fix": True,
                "need_metadata": True,
                "need_rag": False,
            }
        ),
        critic_agent=SQLCriticAgent(),
    )

    result = workflow.run(
        sql="select * from unknown_table",
        file_path="test.sql",
    )

    assert result.success is False
    assert result.final_status == "context_required"
    assert result.route_history == [
        "explain",
        "review",
    ]
    assert result.fix_response is None