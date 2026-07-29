from dataclasses import dataclass, field
from typing import Any

from sql_review_agent.schemas.responses import SQLFixResponse, SQLReviewResponse


@dataclass
class SQLCriticResponse:

    success: bool
    passed: bool
    trace_id: str | None = None
    status: str = "unknown"
    reason: str = ""
    need_human_confirm: bool = False
    need_retry: bool = False
    checked_items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None

    retry_instructions: list[str] = field(default_factory=list)
    raw_output: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "passed": self.passed,
            "trace_id": self.trace_id,
            "status": self.status,
            "reason": self.reason,
            "need_human_confirm": self.need_human_confirm,
            "need_retry": self.need_retry,
            "checked_items": self.checked_items,
            "warnings": self.warnings,
            "error_message": self.error_message,
            "retry_instructions": self.retry_instructions,
            "raw_output": self.raw_output,
        }
    

    @classmethod
    def from_llm_payload(
        cls,
        payload: dict[str, Any],
        trace_id: str | None = None,
        raw_output: Any | None = None,
    ) -> "SQLCriticResponse":
        
        passed = bool(payload.get("passed", False))
        need_retry = bool(payload.get("need_retry", False))
        need_human_confirm = bool(
            payload.get("need_human_confirm", False)
        )

        return cls(
            success=True,
            passed=passed,
            trace_id=trace_id,
            status=payload.get(
                "status",
                "passed" if passed else "failed",
            ),
            reason=payload.get("reason",""),
            need_retry=need_retry,
            need_human_confirm=need_human_confirm,
            checked_items=payload.get("checked_items", []),
            warnings=payload.get("warnings", []),
            retry_instructions=payload.get("retry_instructions", []),
            raw_output=raw_output,
        )



class SQLCriticService:

    def critique(self, review_response: SQLReviewResponse, fix_response: SQLFixResponse, re_review_response: SQLReviewResponse | None = None, trace_id: str| None = None,) -> SQLCriticResponse:
        try: 
            checked_items: list[dict[str, Any]] = []
            warnings: list[str] = []

            if not fix_response.success:
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="fix_failed",
                    reason="Fix response indicates failed",
                    need_human_confirm=True,
                    checked_items=[
                        {
                            "name":"fix_success",
                            "passed":False,
                            "detail":fix_response.error_message,
                        }
                    ],
                )

            checked_items.append(
                {
                    "name": "fix_success",
                    "passed": True,
                    "detail": "Fix response succeeded.",
                }
            )

            if not fix_response.fixed_sql:
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="no_fixed_sql",
                    reason="Fix did not produce fixed_sql",
                    need_human_confirm=True,
                    checked_items=checked_items
                    + [
                        {
                            "name": "fixed_sql_exists",
                            "passed": False,
                            "detail": "fixed_sql is empty.",
                        }
                    ],
                )

            checked_items.append(
                {
                    "name": "fixed_sql_exists",
                    "passed": True,
                    "detail": "fixed_sql exists.",
                }
            )

            if review_response.issue_count > 0 and not fix_response.applied_fixes:
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="no_applied_fixes",
                    reason="Review found issues but Fix did not record applied_fixes.",
                    need_human_confirm=True,
                    checked_items=checked_items
                    + [
                        {
                            "name": "applied_fixes_recorded",
                            "passed": False,
                            "detail": "applied_fixes is empty.",
                        }
                    ],
                )

            checked_items.append(
                {
                    "name": "applied_fixes_recorded",
                    "passed": True,
                    "detail": "applied_fixes is recorded.",
                }
            )

            if re_review_response is None:
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="re_review_missing",
                    reason="Fixed SQL was not reviewed again.",
                    need_human_confirm=True,
                    need_retry=True,
                    checked_items=checked_items
                    + [
                        {
                            "name": "re_review_exists",
                            "passed": False,
                            "detail": "No re-review response was provided.",
                        }
                    ],
                )

            if not re_review_response.success:
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="re_review_failed",
                    reason="Reviewing the fixed SQL failed.",
                    need_human_confirm=True,
                    need_retry=True,
                    checked_items=checked_items
                    + [
                        {
                            "name": "re_review_success",
                            "passed": False,
                            "detail": re_review_response.error_message,
                        }
                    ],
                )

            checked_items.append(
                {
                    "name": "re_review_success",
                    "passed": True,
                    "detail": "Fixed SQL was reviewed successfully.",
                }
            )

            if re_review_response.issue_count > 0:
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="issues_remaining",
                    reason=(
                        f"Fixed SQL still has "
                        f"{re_review_response.issue_count} issue(s)."
                    ),
                    need_human_confirm=True,
                    checked_items=checked_items
                    + [
                        {
                            "name": "remaining_issue_count",
                            "passed": False,
                            "detail": (
                                f"Original issues: {review_response.issue_count}; "
                                f"remaining issues: "
                                f"{re_review_response.issue_count}."
                            ),
                        }
                    ],
                    warnings=[
                        "The fixed SQL did not pass deterministic re-review."
                    ],
                )

            checked_items.append(
                {
                    "name": "remaining_issue_count",
                    "passed": True,
                    "detail": (
                        f"Original issues: {review_response.issue_count}; "
                        "remaining issues: 0."
                    ),
                }
            )

            if fix_response.manual_notes:
                warnings.append("Fix response contains manual_notes; human review may still be needed.")

                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="need_human_confirm",
                    reason="Fix contains manual_notes requiring human confirmation.",
                    need_human_confirm=True,
                    checked_items=checked_items,
                    warnings=warnings,
                )

            return SQLCriticResponse(
                success=True,
                passed=True,
                trace_id=trace_id,
                status="passed",
                reason="Fixed SQL passed deterministic re-review.",
                need_human_confirm=False,
                checked_items=checked_items,
                warnings=warnings,
            )

        except Exception as error:
            return SQLCriticResponse(
                success=False,
                passed=False,
                trace_id=trace_id,
                status="critic_error",
                reason="Critic execution failed.",
                need_human_confirm=True,
                error_message=str(error),
            )
        



import json
from typing import Protocol

from sql_review_agent.llm.json_repair import JSONRepairer
from sql_review_agent.llm.json_utils import parse_json_object


class CriticLLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...
    

class LLMSQLCriticService:

    def __init__(
            self,
            llm_client: CriticLLMClient,
            json_repairer: JSONRepairer | None = None,
            fallback_agent: SQLCriticService | None = None,
    ):
        self.llm_client = llm_client
        self.json_repairer = json_repairer
        self.fallback_agent = fallback_agent or SQLCriticService()

    
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
            return self.fallback_agent.critique(
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