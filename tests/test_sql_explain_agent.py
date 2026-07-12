from sql_review_agent.agents.sql_explain_agent import SQLExplainAgent
from sql_review_agent.schemas.requests import SQLExplainRequest
from sql_review_agent.llm.json_repair import JSONRepairer


class BrokenThenRepairableLLM:
    def complete(self, prompt: str) -> str:
        return "sql_summary: 该 SQL 可被修复为 JSON"
    
class RepairLLM:
    def complete(self, prompt: str) -> str:
        return """
        {
          "sql_summary": "该 SQL 可被修复为 JSON",
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

class BrokenRepairLLM:
    def complete(self, prompt: str) -> str:
        return "still not json"


class MockExplainLLM:
    def complete(self, prompt: str) -> str:
        return """
        {
          "sql_summary": "该 SQL 汇总用户订单金额。",
          "business_purpose": "生成用户订单汇总结果。",
          "main_tables": [
            {
              "table_name": "dwd_order",
              "alias": "o",
              "role": "fact_table",
              "usage": "提供订单明细",
              "confidence": 0.9
            }
          ],
          "output_columns": [
            {
              "column_name": "total_amt",
              "meaning": "订单总金额",
              "source": "sum(o.amount)",
              "risk": null
            }
          ],
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


class BrokenLLM:
    def complete(self, prompt: str) -> str:
        return "not json"


def test_explain_agent_should_repair_invalid_json_output():

    agent = SQLExplainAgent(llm_client=BrokenThenRepairableLLM(), json_repairer=JSONRepairer(llm_client=RepairLLM()))

    response = agent.explain(SQLExplainRequest(sql = "SELECT 1", file_path="repair.sql"), trace_id="trace-repair")

    assert response.success is True
    assert response.trace_id == "trace-repair"
    assert response.sql_summary == "该 SQL 可被修复为 JSON"
    assert response.route_signals["next_node"] == "review_agent"


def text_explain_agent_should_fail_when_repair_still_invalid():

    agent = SQLExplainAgent(llm_client=BrokenThenRepairableLLM(), json_repairer=JSONRepairer(llm_client=BrokenRepairLLM()))

    response = agent.explain(SQLExplainRequest(sql = "SELECT 1", file_path="repair.sql"), trace_id="trace-repair-failed")
 
    assert response.success is False
    assert response.trace_id == "trace-repair-failed"
    assert response.file_path == "repair_failed.sql"
    assert response.error_message is not None
    assert response.route_signals["next_node"] == "fallback_review"
    assert response.raw_output is not None

def test_explain_agent_should_return_structured_response():
    agent = SQLExplainAgent(llm_client=MockExplainLLM())

    response = agent.explain(
        SQLExplainRequest(
            sql="select user_id, sum(amount) as total_amt from dwd_order o group by user_id",
            file_path="order.sql",
        ),
        trace_id="trace-001",
    )
    print(response.error_message)

    # TODO 7:
    # 断言：
    # - success is True
    # - trace_id == "trace-001"
    # - sql_summary
    # - main_tables[0]["table_name"]
    # - route_signals["next_node"] == "review_agent"
    assert response.success is True
    assert response.task_type == "explain"
    assert response.file_path == "order.sql"
    assert response.trace_id == "trace-001"
    assert response.sql_summary == "该 SQL 汇总用户订单金额。"
    assert response.business_purpose == "生成用户订单汇总结果。"
    assert response.main_tables[0]["table_name"] == "dwd_order"
    assert response.output_columns[0]["column_name"] == "total_amt"
    assert response.route_signals["next_node"] == "review_agent"



def test_explain_agent_should_return_failed_response_when_json_invalid():
    agent = SQLExplainAgent(llm_client=BrokenLLM())

    response = agent.explain(
        SQLExplainRequest(sql="select 1", file_path="broken.sql"),
        trace_id="trace-broken",
    )

    # TODO 8:
    # 断言：
    # - success is False
    # - trace_id == "trace-broken"
    # - error_message 不为空
    # - route_signals["next_node"] == "fallback_review"
    assert response.success is False
    assert response.task_type == "explain"
    assert response.file_path == "broken.sql"
    assert response.trace_id == "trace-broken"
    assert response.error_message is not None
    assert response.route_signals["next_node"] == "fallback_review"