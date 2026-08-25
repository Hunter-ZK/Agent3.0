from dataclasses import dataclass, field, replace
from uuid import uuid4

from typing import Any

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
from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.core.execution_context import (
    SQLExecutionContext,
)

from sql_pilot_engine.core.models import (
    IssueAction,
)

@dataclass
class TrustedSQLWorkflowResult:
    success: bool
    trace_id: str
    final_status: str

    missing_context: tuple[str, ...] = ()
    
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

class TrustedSQLWorkflow:
    """SQL Agent模式的端到端流程。"""

    def __init__(
        self,
        engine: SQLPilotEngine,
        max_retries: int = 1,
        default_enable_metadata: bool = False,
        default_enable_llm: bool = True,
        default_llm_provider: str = "deepseek",
        default_fix_provider: str = "llm",
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

        self.default_enable_llm = (
            default_enable_llm
        )

        self.default_llm_provider = (
            default_llm_provider
        )

        self.default_fix_provider = (
            default_fix_provider
        )

    def run(
        self,
        sql: str,
        file_path: str = "<memory>",
        *,
        mode: str = "prod",
        dialect: str = "maxcompute",
        query_context: QueryContext | None = None,
        categories: set[str] | None = None,
        enable_metadata: bool | None = None,
        enable_llm: bool | None = None,
        llm_provider: str | None = None,
        fix_provider: str | None = None,
    ) -> TrustedSQLWorkflowResult:


        trace_id = str(uuid4())
        route_history: list[str] = []
        
        explain_response = None

        enable_metadata = (
            self.default_enable_metadata
            if enable_metadata is None
            else enable_metadata
        )

        enable_llm = (
            self.default_enable_llm
            if enable_llm is None
            else enable_llm
        )

        llm_provider = (
            self.default_llm_provider
            if llm_provider is None
            else llm_provider
        )

        fix_provider = (
            self.default_fix_provider
            if fix_provider is None
            else fix_provider
        )

        # 测试或显式关闭 LLM 时，
        # 不应该还要求 LLM Fix。
        if (
            not enable_llm
            and fix_provider == "llm"
        ):
            fix_provider = "auto"

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
                    mode=mode,
                    dialect=dialect,
                    query_context=query_context,
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
                mode=mode,
                dialect=dialect,
                query_context=query_context,
            )
        )


        route_history.append("review")

        if not review_response.success:
            return TrustedSQLWorkflowResult(
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

        print("\n" + "=" * 80)
        print("[TRUST DEBUG] SQL")
        print("=" * 80)
        print(sql)

        print("\n[TRUST DEBUG] QUERY CONTEXT")

        if query_context is None:
            print("query_context = None")
        else:
            print(
                "question =",
                query_context.question,
            )

            print(
                "\nsemantic_context ="
            )
            print(
                query_context.semantic_context
            )

            print(
                "\nbusiness_knowledge ="
            )
            for item in (
                query_context.business_knowledge
            ):
                print("-", item)

            print(
                "\nsession_context ="
            )
            for item in (
                query_context.session_context
            ):
                print("-", item)

        print("\n[TRUST DEBUG] REVIEW")

        print(
            "review_success =",
            review_response.success,
        )

        print(
            "risk_level =",
            review_response.risk_level,
        )

        print(
            "issue_count =",
            review_response.issue_count,
        )

        for index, issue in enumerate(
            review_response.issues,
            start=1,
        ):
            print(
                f"\n--- issue {index} ---"
            )

            for key in (
                "rule_id",
                "title",
                "source",
                "severity",
                "action",
                "requires_metadata",
                "requires_knowledge",
                "blocking",
                "confidence",
                "message",
                "suggestion",
                "evidence",
                "metadata",
            ):
                print(
                    f"{key} =",
                    issue.get(key),
                )


        decision = decide_review_route(review_response)
        
        print(
            "\n[TRUST DEBUG] ROUTE"
        )

        print(
            "route =",
            decision.route.value,
        )

        print(
            "final_status =",
            decision.final_status,
        )

        print(
            "reason =",
            decision.reason,
        )

        print(
            "actionable_issue_count =",
            decision.actionable_issue_count,
        )

        print("=" * 80 + "\n")
        
        if decision.route == ReviewRoute.COMPLETE:
            return TrustedSQLWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status=decision.final_status or "completed",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                # Review 已经确认当前 SQL
                # 可以进入 Trusted 状态。
                trusted_sql=sql,

                # Optimization 尚未进入 Workflow，
                # 所以当前 final_sql == trusted_sql。
                final_sql=sql,

                optimization_applied=False,
            )


        missing_context = ()

        if (
            decision.route
            is ReviewRoute.CONTEXT_REQUIRED
        ):
            missing_context = (
                self._collect_missing_context(
                    review_response
                )
            )

            return TrustedSQLWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status=(
                    decision.final_status
                    or "review_failed"
                ),
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=decision.reason,
                missing_context=missing_context,
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
                    mode=mode,
                    dialect=dialect,
                    query_context=query_context,
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
                            mode=mode,
                            dialect=dialect,
                            query_context=query_context,
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
                
            if (
                re_review_response is not None
                and re_review_response.success
            ):
                re_review_decision = (
                    decide_review_route(
                        re_review_response
                    )
                )

                if (
                    re_review_decision.route
                    is ReviewRoute.CONTEXT_REQUIRED
                ):
                    return TrustedSQLWorkflowResult(
                        success=False,
                        trace_id=trace_id,
                        final_status=(
                            "context_required"
                        ),
                        explain_response=(
                            explain_response
                        ),
                        review_response=(
                            review_response
                        ),
                        fix_response=(
                            fix_response
                        ),
                        re_review_response=(
                            re_review_response
                        ),
                        route_history=(
                            route_history
                        ),
                        error_message=(
                            re_review_decision.reason
                        ),
                        missing_context=(
                            self._collect_missing_context(
                                re_review_response
                            )
                        ),
                    )

                if (
                    re_review_decision.route
                    is ReviewRoute.BLOCK
                ):
                    return TrustedSQLWorkflowResult(
                        success=False,
                        trace_id=trace_id,
                        final_status="blocked",
                        explain_response=explain_response,
                        review_response=review_response,
                        fix_response=fix_response,
                        re_review_response=(
                            re_review_response
                        ),
                        route_history=route_history,
                        error_message=(
                            re_review_decision.reason
                        ),
                    )

                if (
                    re_review_decision.route
                    is ReviewRoute.HUMAN_REVIEW
                ):
                    return TrustedSQLWorkflowResult(
                        success=False,
                        trace_id=trace_id,
                        final_status=(
                            "need_human_confirm"
                        ),
                        explain_response=explain_response,
                        review_response=review_response,
                        fix_response=fix_response,
                        re_review_response=(
                            re_review_response
                        ),
                        route_history=route_history,
                        error_message=(
                            re_review_decision.reason
                        ),
                    )

            print("\n" + "=" * 80)
            print("[TRUST DEBUG] FIX RESULT")
            print("=" * 80)

            print(
                "fix_success =",
                fix_response.success,
            )

            print(
                "\nfixed_sql ="
            )

            print(
                fix_response.fixed_sql
            )

            print(
                "\napplied_fixes =",
                fix_response.applied_fixes,
            )

            print(
                "manual_notes =",
                fix_response.manual_notes,
            )

            print(
                "fix_source =",
                fix_response.fix_source,
            )


            print(
                "\n[TRUST DEBUG] RE-REVIEW"
            )

            if re_review_response is None:

                print(
                    "re_review_response = None"
                )

            else:

                print(
                    "success =",
                    re_review_response.success,
                )

                print(
                    "risk_level =",
                    re_review_response.risk_level,
                )

                print(
                    "issue_count =",
                    re_review_response.issue_count,
                )

                for index, issue in enumerate(
                    re_review_response.issues,
                    start=1,
                ):

                    print(
                        f"\n--- re-review issue {index} ---"
                    )

                    for key in (
                        "rule_id",
                        "title",
                        "source",
                        "severity",
                        "action",
                        "requires_metadata",
                        "requires_knowledge",
                        "blocking",
                        "confidence",
                        "message",
                        "suggestion",
                        "evidence",
                        "metadata",
                    ):
                        print(
                            f"{key} =",
                            issue.get(key),
                        )

                if re_review_response.success:

                    re_review_decision = (
                        decide_review_route(
                            re_review_response
                        )
                    )

                    print(
                        "\nre_review_route =",
                        re_review_decision.route.value,
                    )

                    print(
                        "re_review_final_status =",
                        re_review_decision.final_status,
                    )

                    print(
                        "re_review_reason =",
                        re_review_decision.reason,
                    )

            print("=" * 80 + "\n")

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

            print(
                "\n[TRUST DEBUG] CRITIC"
            )

            print(
                "passed =",
                critic_response.passed,
            )

            print(
                "status =",
                critic_response.status,
            )

            print(
                "need_retry =",
                critic_response.need_retry,
            )

            print(
                "reason =",
                critic_response.reason,
            )

            print(
                "error_message =",
                critic_response.error_message,
            )

            print(
                "retry_instructions =",
                critic_response.retry_instructions,
            )

            print("=" * 80 + "\n")

            if critic_response.passed:

                trusted_sql = (
                    fix_response.fixed_sql
                )

                if not trusted_sql:
                    raise RuntimeError(
                        "Critic passed but fixed_sql "
                        "is missing."
                    )

                return TrustedSQLWorkflowResult(
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

                    trusted_sql=trusted_sql,
                    final_sql=trusted_sql,

                    optimization_applied=False,
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
                return TrustedSQLWorkflowResult(
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
        
            
    @staticmethod
    def _collect_missing_context(
        response: SQLReviewResponse,
    ) -> tuple[str, ...]:

        result: list[str] = []

        for issue in response.issues:

            action = issue.get(
                "action"
            )

            if isinstance(
                action,
                IssueAction,
            ):
                action = action.value

            if (
                action
                != IssueAction
                .CONTEXT_REQUIRED
                .value
            ):
                continue

            for item in (
                issue.get(
                    "missing_context",
                    (),
                )
                or ()
            ):

                value = str(
                    item
                ).strip()

                if (
                    value
                    and value
                    not in result
                ):
                    result.append(
                        value
                    )

        return tuple(result)