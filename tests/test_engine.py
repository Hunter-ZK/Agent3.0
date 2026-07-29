from sql_review_agent.app.factory import build_sql_review_engine
from sql_review_agent.engine import SQLReviewEngine
from sql_review_agent.metadata.provider import MockMetadataProvider
from sql_review_agent.schemas import SQLFixRequest, SQLReviewRequest
from sql_review_agent.services.review_service import ReviewService
from sql_review_agent.agents.sql_explain_agent import SQLExplainAgent
from sql_review_agent.schemas.requests import SQLExplainRequest
import os
class BrokenReviewService:
    def review(self, context):
        raise RuntimeError("Broken review service")
    
def test_engine_review_failed_response_should_keep_trace_id():
    engine = SQLReviewEngine(review_service=BrokenReviewService())
    response = engine.review(SQLReviewRequest(sql="select 1", file_path="broken.sql"))

    assert response.success is False
    assert response.task_type == "review"
    assert response.file_path == "broken.sql"
    assert response.trace_id is not None
    assert "Broken review service" in response.error_message


def test_engine_review_should_return_stable_response():
    engine = SQLReviewEngine()
    request = SQLReviewRequest(sql="select * from dwd_user_order_detail", file_path="memory.sql")

    response = engine.review(request)

    assert response.success is True
    assert response.task_type == "review"
    assert response.file_path == "memory.sql"
    assert response.raw_result is not None
    assert response.issue_count == response.raw_result.issue_count
    assert response.to_dict()["risk_level"] in {"low", "medium", "high"}
    assert response.trace_id is not None
    assert response.to_dict()["trace_id"] == response.trace_id


def test_engine_review_should_match_review_service_result():
    sql = "select * from dwd_user_order_detail where dt = '20260601'"
    service = ReviewService()
    engine = SQLReviewEngine(review_service=service)

    service_result = service.review_sql(sql=sql, file_path="memory.sql")
    engine_response = engine.review(SQLReviewRequest(sql=sql, file_path="memory.sql"))

    assert engine_response.success is True
    assert engine_response.raw_result is not None
    assert engine_response.issue_count == service_result.issue_count
    assert engine_response.risk_level == service_result.risk_level.value


def test_engine_fix_should_return_fixed_sql_fields():
    sql = "select user_id from dwd_user_order_detail where dt = '20260601'"
    engine = SQLReviewEngine()

    response = engine.fix(SQLFixRequest(sql=sql, fix_provider="auto"))

    assert response.success is True
    assert response.task_type == "fix"
    assert response.raw_result is not None
    assert response.fixed_sql is not None
    assert "dt = '${bizdate}'" in response.fixed_sql
    assert response.fix_source == "auto"
    assert response.trace_id is not None
    assert response.to_dict()["trace_id"] == response.trace_id


def test_engine_should_create_mock_metadata_provider_when_enabled():
    sql = "select user_id, pay_amt from dwd_user_order_detail where dt = '${bizdate}'"
    engine = SQLReviewEngine()

    response = engine.review(SQLReviewRequest(sql=sql, enable_metadata=True))

    assert response.success is True
    assert any(issue["rule_id"] == "UNKNOWN_COLUMN" for issue in response.issues)


def test_engine_should_accept_explicit_metadata_provider():
    sql = "select user_id, pay_amt from dwd_user_order_detail where dt = '${bizdate}'"
    engine = SQLReviewEngine()

    response = engine.review(
        SQLReviewRequest(
            sql=sql,
            enable_metadata=False,
            metadata_provider=MockMetadataProvider(),
        )
    )

    assert response.success is True
    assert any(issue["rule_id"] == "UNKNOWN_COLUMN" for issue in response.issues)


def test_factory_should_build_engine():
    engine = build_sql_review_engine()

    response = engine.review(SQLReviewRequest(sql="select 1"))

    assert response.success is True
    assert response.raw_result is not None




class MockEngineExplainLLM:
    def complete(self, prompt: str) -> str:
        return """
        {
          "sql_summary": "该 SQL 查询常量。",
          "business_purpose": null,
          "main_tables": [],
          "output_columns": [],
          "cte_steps": [],
          "cte_dependencies": [],
          "suspicious_points": [],
          "uncertainties": [],
          "route_signals": {
            "need_metadata": false,
            "need_rag": false,
            "need_review": true,
            "need_human_confirm": false,
            "can_auto_fix": false,
            "next_node": "review_agent"
          }
        }
        """


def test_engine_explain_should_use_explain_agent():
    engine = SQLReviewEngine(
        review_service=BrokenReviewService(),
        explain_agent=SQLExplainAgent(llm_client=MockEngineExplainLLM()),
    )

    response = engine.explain(SQLExplainRequest(sql="select 1", file_path="explain.sql"))

    assert response.success is True
    assert response.task_type == "explain"
    assert response.file_path == "explain.sql"
    assert response.trace_id is not None
    assert response.sql_summary == "该 SQL 查询常量。"
    assert response.route_signals["next_node"] == "review_agent"



