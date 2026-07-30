from dataclasses import dataclass, field
from uuid import uuid4

from sql_pilot_engine.engine import SQLPilotEngine
from sql_pilot_engine.schemas.requests import (
    SQLExplainRequest,
    SQLFixRequest,
    SQLReviewRequest,
)
from sql_pilot_engine.schemas.responses import (
    SQLCriticResponse,
    SQLExplainResponse,
    SQLFixResponse,
    SQLReviewResponse,
)


@dataclass
class SQLAgentWorkflowResult:
    success: bool
    trace_id: str
    final_status: str

    explain_response: (
        SQLExplainResponse | None
    ) = None

    review_response: (
        SQLReviewResponse | None
    ) = None

    fix_response: SQLFixResponse | None = None

    re_review_response: (
        SQLReviewResponse | None
    ) = None

    critic_response: (
        SQLCriticResponse | None
    ) = None

    route_history: list[str] = field(
        default_factory=list
    )

    error_message: str | None = None


class SQLAgentWorkflow:
    """SQL Agent模式的端到端流程。"""

    def __init__(
        self,
        engine: SQLPilotEngine,
        max_retries: int = 1,
    ) -> None:
        if max_retries < 0:
            raise ValueError(
                "max_retries cannot be negative."
            )

        self.engine = engine
        self.max_retries = max_retries

    def run(
        self,
        sql: str,
        file_path: str = "",
    ) -> SQLAgentWorkflowResult:
        trace_id = str(uuid4())
        route_history: list[str] = []

        explain_response = self.engine.explain(
            SQLExplainRequest(
                sql=sql,
                file_path=file_path,
                trace_id=trace_id,
            )
        )

        route_history.append("explain")

        if not explain_response.success:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="explain_failed",
                explain_response=explain_response,
                route_history=route_history,
                error_message=(
                    explain_response.error_message
                ),
            )

        signals = (
            explain_response.route_signals
            if isinstance(
                explain_response.route_signals,
                dict,
            )
            else {}
        )

        if not signals.get("need_review", True):
            return SQLAgentWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status="explained",
                explain_response=explain_response,
                route_history=route_history,
            )

        review_response = self.engine.review(
            SQLReviewRequest(
                sql=sql,
                file_path=file_path,
                trace_id=trace_id,
            )
        )

        route_history.append("review")

        if not review_response.success:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="review_failed",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=(
                    review_response.error_message
                ),
            )

        if review_response.issue_count == 0:
            return SQLAgentWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status="no_issue",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        if signals.get("need_rag", False):
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="knowledge_required",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        if signals.get("need_metadata", False):
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="metadata_required",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        if (
            signals.get(
                "need_human_confirm",
                False,
            )
            or not signals.get(
                "can_auto_fix",
                False,
            )
        ):
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status=(
                    "need_human_confirm"
                ),
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        current_sql = sql
        critic_feedback: list[str] = []

        for attempt in range(
            self.max_retries + 1
        ):
            fix_response = self.engine.fix(
                SQLFixRequest(
                    sql=current_sql,
                    file_path=file_path,
                    trace_id=trace_id,
                    retry_count=attempt,
                    critic_feedback=critic_feedback,
                )
            )

            route_history.append(
                "fix"
                if attempt == 0
                else f"fix_retry_{attempt}"
            )

            re_review_response = None

            if (
                fix_response.success
                and fix_response.fixed_sql
            ):
                re_review_response = (
                    self.engine.review(
                        SQLReviewRequest(
                            sql=(
                                fix_response.fixed_sql
                            ),
                            file_path=file_path,
                            trace_id=trace_id,
                        )
                    )
                )

                route_history.append(
                    "re_review"
                    if attempt == 0
                    else (
                        f"re_review_retry_"
                        f"{attempt}"
                    )
                )

            critic_response = (
                self.engine.critique(
                    review_response=(
                        review_response
                    ),
                    fix_response=fix_response,
                    re_review_response=(
                        re_review_response
                    ),
                    trace_id=trace_id,
                )
            )

            route_history.append("critic")

            if critic_response.passed:
                return SQLAgentWorkflowResult(
                    success=True,
                    trace_id=trace_id,
                    final_status="fix_verified",
                    explain_response=(
                        explain_response
                    ),
                    review_response=(
                        review_response
                    ),
                    fix_response=fix_response,
                    re_review_response=(
                        re_review_response
                    ),
                    critic_response=(
                        critic_response
                    ),
                    route_history=route_history,
                )

            can_retry = (
                critic_response.need_retry
                and attempt < self.max_retries
                and bool(fix_response.fixed_sql)
            )

            if not can_retry:
                return SQLAgentWorkflowResult(
                    success=False,
                    trace_id=trace_id,
                    final_status=(
                        "need_human_confirm"
                    ),
                    explain_response=(
                        explain_response
                    ),
                    review_response=(
                        review_response
                    ),
                    fix_response=fix_response,
                    re_review_response=(
                        re_review_response
                    ),
                    critic_response=(
                        critic_response
                    ),
                    route_history=route_history,
                )

            current_sql = (
                fix_response.fixed_sql
                or current_sql
            )

            critic_feedback = (
                critic_response
                .retry_instructions
            )

        raise RuntimeError(
            "Workflow reached an invalid state."
        )