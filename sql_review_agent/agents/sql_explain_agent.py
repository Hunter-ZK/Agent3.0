from typing import Protocol

from sql_review_agent.llm.json_utils import parse_json_object
from sql_review_agent.schemas.requests import SQLExplainRequest
from sql_review_agent.schemas.responses import SQLExplainResponse
from sql_review_agent.llm.json_repair import JSONRepairer

class LLMClient(Protocol):
    """ExplainAgent 需要的最小 LLM Client 协议。"""

    def complete(self, prompt: str) -> str:
        ...


class SQLExplainAgent:
    """LLM-first SQL Explain Agent。

    责任：
    1. 构造 explain prompt；
    2. 调用 LLM；
    3. 解析结构化 JSON；
    4. 转成 SQLExplainResponse。
    """

    def __init__(self, llm_client: LLMClient, json_repairer: JSONRepairer | None = None,):
        self.llm_client = llm_client
        self.json_repairer = json_repairer

    def explain(self, request: SQLExplainRequest, trace_id: str | None = None) -> SQLExplainResponse:
        # TODO 5:
        # 1. build prompt
        # 2. llm_client.complete(prompt)
        # 3. parse_json_object
        # 4. SQLExplainResponse.from_llm_payload(...)
        # 5. except 时返回 SQLExplainResponse.failed(...)
        
        try:
            explain_prompt = self._build_prompt(request)
            # print(explain_prompt)
            llm_output = self.llm_client.complete(explain_prompt)
            raw_output = llm_output

            try:
                payload  = parse_json_object(llm_output)
            except ValueError:
                if self.json_repairer is None:
                    raise

                repaired_output = self.json_repairer.repair(
                    broken_text=llm_output,
                    schema_hint=self._schema_hint(),
                )
                payload = parse_json_object(repaired_output)

            return SQLExplainResponse.from_llm_payload(payload=payload ,file_path=request.file_path, trace_id=trace_id,)
        except Exception as e:
            return SQLExplainResponse.failed(file_path=request.file_path, error_message=str(e), trace_id=trace_id, raw_output=raw_output,)


    def _schema_hint(self) -> str:
        return """
    {
    "sql_summary": "string",
    "business_purpose": "string or null",
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
    """.strip()

    def _build_prompt(self, request: SQLExplainRequest) -> str:
        return f"""
你是 MaxCompute SQL Explain Agent。

请分析下面 SQL，并且只返回一个 JSON object。
不要返回 markdown，不要返回解释性正文，不要使用 ```json 代码块。

JSON object 必须尽量包含以下字段：

{{
  "sql_summary": "string",
  "business_purpose": "string or null",
  "main_tables": [
    {{
      "table_name": "string",
      "alias": "string or null",
      "role": "fact_table|dimension_table|unknown",
      "usage": "string",
      "confidence": 0.0
    }}
  ],
  "output_columns": [
    {{
      "column_name": "string",
      "meaning": "string or null",
      "source": "string or null",
      "risk": "string or null"
    }}
  ],
  "cte_steps": [
    {{
      "cte_name": "string",
      "purpose": "string",
      "input_tables": [],
      "input_ctes": [],
      "output_columns": [],
      "key_filters": [],
      "key_joins": []
    }}
  ],
  "cte_dependencies": [
    {{
      "from": "string",
      "to": "string",
      "relation": "string",
      "risk": "string or null"
    }}
  ],
  "suspicious_points": [
    {{
      "type": "string",
      "severity": "low|medium|high",
      "description": "string",
      "need_metadata": false,
      "need_rag": false,
      "need_human_confirm": false
    }}
  ],
  "uncertainties": [],
  "route_signals": {{
    "need_metadata": false,
    "need_rag": false,
    "need_review": true,
    "need_human_confirm": false,
    "can_auto_fix": false,
    "next_node": "review_agent"
  }}
}}

SQL:
{request.sql}
""".strip()