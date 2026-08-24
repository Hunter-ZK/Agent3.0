
from typing import Any

from sql_pilot_engine.schemas.responses import SQLFixResponse, SQLReviewResponse,SQLCriticResponse

from sql_pilot_engine.workflow.review_routing import (
    ReviewRoute,
    decide_review_route,
)

class CriticService:

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

            re_review_decision = (
                decide_review_route(
                    re_review_response
                )
            )

            if (
                re_review_decision.route
                != ReviewRoute.COMPLETE
            ):
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="issues_remaining",
                    reason=(
                        "Fixed SQL still contains "
                        "trust-gating issues: "
                        f"{re_review_decision.reason}"
                    ),
                    need_retry=(
                        re_review_decision.route
                        == ReviewRoute.AUTO_FIX
                    ),
                    need_human_confirm=(
                        re_review_decision.route
                        != ReviewRoute.AUTO_FIX
                    ),
                    checked_items=(
                        checked_items
                        + [
                            {
                                "name": (
                                    "trust_gate"
                                ),
                                "passed": False,
                                "detail": (
                                    re_review_decision
                                    .reason
                                ),
                            }
                        ]
                    ),
                    retry_instructions=(
                        [
                            (
                                "根据复审仍存在的 "
                                "trust-gating issues "
                                "继续修复 SQL。"
                            )
                        ]
                        if (
                            re_review_decision.route
                            == ReviewRoute.AUTO_FIX
                        )
                        else []
                    ),
                )

            checked_items.append(
                {
                    "name": (
                        "trust_gating_issues_remaining"
                    ),
                    "passed": True,
                    "detail": (
                        "Re-review issue count: "
                        f"{re_review_response.issue_count}; "
                        "no trust-gating issues remain."
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
                reason="Fixed SQL passed trusted re-review.",
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
        


