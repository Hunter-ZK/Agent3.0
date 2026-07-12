from dataclasses import dataclass, field
from typing import Any

from sql_review_agent.schemas.responses import SQLFixResponse, SQLReviewResponse


@dataclass
class SQLCriticResponse:

    success: bool
    passed: bool
    trace_id: str | None = None
    stauts: str = "unknown"
    reason: str = ""
    need_human_confirm: bool = False
    need_retry: bool = False
    checked_items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None

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
        }
    

class SQLCriticAgent:

    def critique(self, review_response: SQLReviewResponse, fix_response: SQLFixResponse, trace_id: str| None = None,) -> SQLCriticResponse:
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
                reason="Minimal deterministic critic passed.",
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