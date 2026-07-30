


import json
from typing import Protocol

from sql_pilot_engine.llm.json_repair import JSONRepairer
from sql_pilot_engine.llm.json_utils import parse_json_object
from sql_pilot_engine.services.critic_service import CriticService
from sql_pilot_engine.schemas.responses import SQLExplainResponse,SQLReviewResponse,SQLFixResponse,SQLCriticResponse

class CriticLLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...
    

class SQLCriticAgent:

    def __init__(
        self,
        llm_client,
        json_repairer=None,
        fallback_service=None,
    ):
        self.llm_client = llm_client
        self.json_repairer = json_repairer
        self.fallback_service = (
            fallback_service
            or CriticService()
        )

    def critique(
            self,
            original_sql: str,
            review_response: SQLReviewResponse,
            fix_response: SQLFixResponse,
            re_review_response: SQLReviewResponse | None = None,
            trace_id: str | None = None,
    ) -> SQLCriticResponse:
        
        raw_output = None

        try:
            prompt = self._build_prompt(
                original_sql=original_sql,
                review_response=review_response,
                fix_response=fix_response,
            )

            raw_output = self.llm_client.complete(prompt)

            try:
                payload = parse_json_object(raw_output)
            except ValueError:
                if self.json_repairer is None:
                    raise

                repaired = self.json_repairer.repair(
                    broken_text=raw_output,
                    schema_hint=self._schema_hint(),
                )

                payload = parse_json_object(repaired)

            return SQLCriticResponse.from_llm_payload(
                payload=payload,
                trace_id=trace_id,
                raw_output=raw_output,
            )
        
        except Exception:
            return self.fallback_service.critique(
                review_response=review_response,
                fix_response=fix_response,
                re_review_response=re_review_response,
                trace_id=trace_id,
            )
        
    
    def _build_prompt(
            self,
            original_sql: str,
            review_response: SQLReviewResponse,
            fix_response: SQLFixResponse,
    ) -> str:
        issues_json = json.dumps(
            review_response.issues,
            ensure_ascii=False,
            indent=2,
        )
        fixes_json = json.dumps(
            fix_response.applied_fixes,
            ensure_ascii=False,
            indent=2,
        )

        notes_json = json.dumps(
            fix_response.manual_notes,
            ensure_ascii=False,
            indent=2,
        )

        return f"""
    你是 SQL 修复结果 Critic。

    你的任务不是重新编写 SQL，而是验证修复是否可信。

    请检查：
    1. 原 Review Issues 是否被覆盖；
    2. Fixed SQL 是否真正解决问题；
    3. 是否引入新的语法、字段、口径或关联风险；
    4. 是否改变原始业务语义；
    5. 是否应再次修复或转人工确认。

    只返回合法 JSON object，不要 markdown，不要额外文字。

    输出格式：
    {self._schema_hint()}

    原始 SQL：
    {original_sql}

    Review Issues：
    {issues_json}

    Fixed SQL：
    {fix_response.fixed_sql or ""}

    Applied Fixes：
    {fixes_json}

    Manual Notes：
    {notes_json}
    """.strip()

    def _schema_hint(self) -> str:
        return """
    {
    "passed": false,
    "status": "passed|need_retry|need_human_confirm",
    "reason": "string",
    "need_retry": false,
    "need_human_confirm": false,
    "checked_items": [
        {
        "name": "string",
        "passed": false,
        "detail": "string"
        }
    ],
    "warnings": [],
    "retry_instructions": []
    }
    """.strip()