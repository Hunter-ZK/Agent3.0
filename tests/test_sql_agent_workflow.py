from sql_review_agent.schemas.responses import SQLExplainResponse,SQLFixResponse,SQLReviewResponse
from sql_review_agent.workflow.sql_agent_workflow import SQLAgentWorkflow

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
    workflow = SQLAgentWorkflow(engine=FakeEngineNoIssue())

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
    workflow = SQLAgentWorkflow(engine=FakeEngineFixVerified())
    result = workflow.run(sql = "select 1", file_path="fix.sql")

    assert result.success is True
    assert result.final_status == "fix_verified"
    assert result.route_history == ["explain", "review", "fix", "critic"]

    assert result.explain_response.trace_id == result.trace_id
    assert result.review_response.trace_id == result.trace_id
    assert result.fix_response.trace_id == result.trace_id

    assert result.critic_response["passed"] is True
    assert result.critic_response is not None
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
    workflow = SQLAgentWorkflow(engine=FakeEngineFixNeedsHuman())

    result = workflow.run(sql="select 1", file_path="human.sql")

    assert result.success is False
    assert result.final_status == "need_human_confirm"
    assert result.route_history == ["explain", "review", "fix", "critic"]
    assert result.critic_response["passed"] is False
    assert result.critic_response["need_human_confirm"] is True