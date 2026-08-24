# sql_review_agent/llm/fixer.py

from typing import Any

from sql_pilot_engine.core.models import FixedSqlResult
from sql_pilot_engine.llm.clients import BaseLLMClient
from sql_pilot_engine.llm.errors import LLMResponseValidationError
from sql_pilot_engine.llm.fix_prompts import (
    FIX_JSON_SCHEMA,
    FIX_REPAIR_SYSTEM_PROMPT,
    FIX_SYSTEM_PROMPT,
    build_fix_repair_prompt,
    build_fix_user_prompt,
)


class LLMFixer:
    """LLM SQL 修复器。"""

    def __init__(self, client: BaseLLMClient) -> None:
        self.client = client

    def fix(
        self,
        original_sql: str,
        deterministic_pre_fix_sql: str,
        rule_issues_text: str,
        analysis_context_text: str,
        metadata_context_text: str,
    ) -> FixedSqlResult:
        user_prompt = build_fix_user_prompt(
            original_sql=original_sql,
            deterministic_pre_fix_sql=deterministic_pre_fix_sql,
            rule_issues_text=rule_issues_text,
            analysis_context_text=analysis_context_text,
            metadata_context_text=metadata_context_text,
        )

        raw_result = self.client.generate_json(
            system_prompt=FIX_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=FIX_JSON_SCHEMA,
        )

        try:
            return self._parse_result(raw_result)
        except LLMResponseValidationError as first_error:
            repair_prompt = build_fix_repair_prompt(raw_result=raw_result, error_message=str(first_error))
            repaired_result = self.client.generate_json(
                system_prompt=FIX_REPAIR_SYSTEM_PROMPT,
                user_prompt=repair_prompt,
                json_schema=FIX_JSON_SCHEMA,
            )
            return self._parse_result(repaired_result)

    def _parse_result(self, raw_result: dict[str, Any]) -> FixedSqlResult:
        if not isinstance(raw_result, dict):
            raise LLMResponseValidationError("LLM Fix 返回结果必须是 JSON object。")

        required_fields = {"fixed_sql", "applied_fixes", "manual_notes"}
        missing_fields = required_fields - set(raw_result.keys())
        if missing_fields:
            raise LLMResponseValidationError(f"LLM Fix 返回结果缺少字段：{sorted(missing_fields)}")

        extra_fields = set(raw_result.keys()) - required_fields
        if extra_fields:
            raise LLMResponseValidationError(f"LLM Fix 返回结果包含多余字段：{sorted(extra_fields)}")

        fixed_sql = raw_result["fixed_sql"]
        applied_fixes = raw_result["applied_fixes"]
        manual_notes = raw_result["manual_notes"]

        if not isinstance(fixed_sql, str):
            raise LLMResponseValidationError("fixed_sql 必须是字符串。")
        if not isinstance(applied_fixes, list):
            raise LLMResponseValidationError("applied_fixes 必须是数组。")
        if not isinstance(manual_notes, list):
            raise LLMResponseValidationError("manual_notes 必须是数组。")

        return FixedSqlResult(
            fixed_sql=fixed_sql,
            applied_fixes=[str(item) for item in applied_fixes],
            manual_notes=[str(item) for item in manual_notes],
            source="llm",
        )
