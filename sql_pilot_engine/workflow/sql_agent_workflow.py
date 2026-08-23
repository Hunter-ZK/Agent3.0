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
    SQLOptimizeResponse,
)
from sql_pilot_engine.workflow.review_routing import (
    ReviewRoute,
    decide_review_route,
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


    optimize_response: (
        SQLOptimizeResponse | None
    ) = None

    optimized_review_response: (
        SQLReviewResponse | None
    ) = None

    trusted_sql: str | None = None

    final_sql: str | None = None

    optimization_applied: bool = False

class SQLAgentWorkflow:
    """SQL Agent模式的端到端流程。"""

    def __init__(
        self,
        engine: SQLPilotEngine,
        max_retries: int = 1,
        default_enable_metadata: bool = False,
    ) -> None:
        if max_retries < 0:
            raise ValueError(
                "max_retries cannot be negative."
            )

        self.engine = engine
        self.max_retries = max_retries

        self.default_enable_metadata = (
            default_enable_metadata
        )

    def run(
        self,
        sql: str,
        file_path: str = "",
        *,
        categories: set[str] | None = None,
        enable_metadata: bool | None = None,
        enable_llm: bool = False,
        llm_provider: str = "mock",
        fix_provider: str = "auto",
    ) -> SQLAgentWorkflowResult:



        trace_id = str(uuid4())
        route_history: list[str] = []
        
        explain_response = None

        enable_metadata = (
            self.default_enable_metadata
            if enable_metadata is None
            else enable_metadata
        )


        if enable_llm and self.engine.explain_available:
            

            explain_response = self.engine.explain(
                SQLExplainRequest(
                    sql=sql,
                    file_path=file_path,
                    categories=categories,
                    enable_metadata=enable_metadata,
                    enable_llm=enable_llm,
                    llm_provider=llm_provider,
                    trace_id=trace_id,
                )
            )

            route_history.append(
                "explain"
                if explain_response.success
                else "explain_failed_continue"
            )
        else:
            route_history.append(
                "explain_skipped"
            )

        review_response = self.engine.review(
            SQLReviewRequest(
                sql=sql,
                file_path=file_path,
                categories=categories,
                enable_metadata=enable_metadata,
                enable_llm=enable_llm,
                llm_provider=llm_provider,
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

        decision = decide_review_route(review_response)
        
        if decision.route == ReviewRoute.COMPLETE:
            return SQLAgentWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status=decision.final_status or "completed",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )


        if decision.route != ReviewRoute.AUTO_FIX:
            if decision.final_status is None:
                raise RuntimeError(
                    "Terminal review route must "
                    "provide final_status."
                )
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status=decision.final_status,
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=decision.reason,
            )
        
        route_history.append(
            f"route:{decision.route.value}"
        )

        current_sql = sql

        # 该变量始终表示current_sql对应的最新Review。
        current_review_response = review_response

        critic_feedback: list[str] = []

        for attempt in range(
            self.max_retries + 1
        ):
            fix_response = self.engine.fix(
                SQLFixRequest(
                    sql=current_sql,
                    file_path=file_path,
                    categories=categories,
                    enable_metadata=enable_metadata,
                    enable_llm=enable_llm,
                    llm_provider=llm_provider,
                    fix_provider=fix_provider,
                    trace_id=trace_id,
                    retry_count=attempt,
                    critic_feedback=critic_feedback,
                ),
                prior_review=(
                    current_review_response
                ),
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
                            sql=fix_response.fixed_sql,
                            file_path=file_path,
                            categories=categories,
                            enable_metadata=(
                                enable_metadata
                            ),
                            enable_llm=enable_llm,
                            llm_provider=llm_provider,
                            trace_id=trace_id,
                        )
                    )
                )

                route_history.append(
                    "re_review"
                    if attempt == 0
                    else (
                        f"re_review_retry_{attempt}"
                    )
                )

            critic_response = (
                self.engine.critique(
                    # Critic检查本轮Fix使用的Review，
                    # 不是永远使用第一次Review。
                    review_response=(
                        current_review_response
                    ),
                    fix_response=fix_response,
                    re_review_response=(
                        re_review_response
                    ),
                    trace_id=trace_id,
                )
            )

            route_history.append(
                "critic"
                if attempt == 0
                else f"critic_retry_{attempt}"
            )

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

            # 只有已经成功复审当前fixed_sql，
            # 才具备下一轮继续修复的可信输入。
            can_retry = (
                critic_response.need_retry
                and attempt < self.max_retries
                and bool(fix_response.fixed_sql)
                and re_review_response is not None
                and re_review_response.success
            )

            if not can_retry:
                return SQLAgentWorkflowResult(
                    success=False,
                    trace_id=trace_id,
                    final_status=(
                        critic_response.status
                        or "need_human_confirm"
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
                    error_message=(
                        critic_response.error_message
                        or critic_response.reason
                    ),
                )

            current_sql = (
                fix_response.fixed_sql
            )

            # 下一轮Fix必须使用当前SQL的复审结果。
            current_review_response = (
                re_review_response
            )

            critic_feedback = (
                critic_response.retry_instructions
            )

        raise RuntimeError(
            "Workflow reached an invalid state."
        )