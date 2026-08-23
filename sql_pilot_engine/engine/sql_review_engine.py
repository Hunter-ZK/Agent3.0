# sql_review_agent/engine/sql_review_engine.py

from collections.abc import Callable
from typing import Any

from sql_pilot_engine.metadata import MetadataProvider, MockMetadataProvider
from sql_pilot_engine.schemas.requests import SQLExplainRequest, SQLFixRequest, SQLOptimizeRequest, SQLReviewRequest
from sql_pilot_engine.schemas.responses import SQLFixResponse, SQLReviewResponse, SQLExplainResponse, SQLCriticResponse, SQLOptimizeResponse
from sql_pilot_engine.services.review_service import ReviewService
from sql_pilot_engine.services.optimize_service import OptimizeService
from sql_pilot_engine.core.execution_context import ReviewExecutionContext
from sql_pilot_engine.core.models import ReviewResult
from sql_pilot_engine.agents.sql_explain_agent import SQLExplainAgent
from sql_pilot_engine.agents.sql_optimize_agent import SQLOptimizeAgent
from sql_pilot_engine.services.critic_service import CriticService
from sql_pilot_engine.services.fix_service import FixService




class SQLPilotEngine:
    """SQLPilot 的稳定 Engine 门面。

    Engine 是外部入口，ReviewService 是内部编排服务。后续 CLI、FastAPI、
    Streamlit、Agent Workflow 都应该优先调用 Engine，而不是直接调用 ReviewService。
    """

    def __init__(
        self,
        review_service: ReviewService,
        fix_service: FixService | None = None,
        metadata_provider_factory: Callable[[], MetadataProvider] | None = None,
        explain_agent: SQLExplainAgent | None = None,
        optimize_service: OptimizeService | None = None,
        critic_service: CriticService | None = None,
    ) -> None:
        self.review_service = (review_service or ReviewService())
        self.fix_service = (fix_service or FixService(review_service=self.review_service))
        self.optimize_service = optimize_service
        if (
            metadata_provider_factory
            is not None
            and not callable(
                metadata_provider_factory
            )
        ):
            raise TypeError(
                "metadata_provider_factory "
                "must be callable or None, "
                f"got "
                f"{type(metadata_provider_factory).__name__}"
            )

        self.metadata_provider_factory = (
            metadata_provider_factory
        )
        self.explain_agent = explain_agent

        self.critic_service = critic_service or CriticService()

    @property
    def explain_available(self) -> bool:
        """当前Engine是否配置了Explain Agent。"""
        return self.explain_agent is not None

    @property
    def optimize_available(self) -> bool:
        return self.optimize_service is not None

    @staticmethod
    def _extract_prior_review_result(
        *,
        prior_review: SQLReviewResponse | None,
        sql: str,
    ) -> ReviewResult | None:
        """提取可安全复用的内部ReviewResult。"""

        if prior_review is None:
            return None

        if not prior_review.success:
            return None

        result = prior_review.raw_result

        if result is None:
            return None

        if not result.reviewed_sql:
            return None

        if result.reviewed_sql != sql:
            raise ValueError(
                "prior_review does not belong "
                "to the SQL being fixed."
            )

        return result

    def review(self, request: SQLReviewRequest) -> SQLReviewResponse:
        """执行 SQL 审查。"""
        context = ReviewExecutionContext.from_review_request(request)
        context.metadata_provider = self._resolve_metadata_provider(context)
        try:
            result = self.review_service.review(context)
            return SQLReviewResponse.from_review_result(result, trace_id=context.trace_id)
        except Exception as error:
            return SQLReviewResponse.failed(
                task_type="review",
                file_path=request.file_path,
                error_message=str(error),
                trace_id=context.trace_id,
            )

    def fix(
        self, 
        request: SQLFixRequest,
        *,
        prior_review: SQLReviewResponse | None = None,
    ) -> SQLFixResponse:
        """先审查 SQL，再生成完整修复 SQL。"""
        context = ReviewExecutionContext.from_fix_request(request)
        context.metadata_provider = self._resolve_metadata_provider(context)
        try:
            review_result = self._extract_prior_review_result(prior_review=prior_review, sql=request.sql,)
            result = self.fix_service.fix(context, review_result=review_result,)
            return SQLFixResponse.from_review_result(result, trace_id=context.trace_id)
        except Exception as error:
            return SQLFixResponse.failed(
                task_type="fix",
                file_path=request.file_path,
                error_message=str(error),
                trace_id=context.trace_id,
            )

    def explain(self, request: SQLExplainRequest) -> SQLExplainResponse:
        """Explain 占位：C 阶段接入 LLM-first 单 Agent 后实现。"""

        context = ReviewExecutionContext.from_review_request(request)

        if self.explain_agent is None:
            return SQLExplainResponse.failed(
                file_path=request.file_path,
                error_message="Explain agent is not configured",
                trace_id=context.trace_id,
            )
        return self.explain_agent.explain(request, trace_id = context.trace_id)
    

    def critique(
        self,
        *,
        review_response: SQLReviewResponse,
        fix_response: SQLFixResponse,
        re_review_response: SQLReviewResponse | None = None,
        trace_id: str | None = None,
    ) -> SQLCriticResponse:
        """验证当前修复结果是否真正通过复审。

        参数前的 * 表示：
        后续参数必须按名称传递，避免多个Response对象因顺序相近而传错。
        """

        return self.critic_service.critique(
            review_response=review_response,
            fix_response=fix_response,
            re_review_response=re_review_response,
            trace_id=trace_id,
        )

    def optimize(
        self,
        request: SQLOptimizeRequest,
        *,
        explain_response: (
            SQLExplainResponse | None
        ) = None,
    ) -> SQLOptimizeResponse:
        """
        SQL Optimization Engine Facade。

        Engine 只负责：
        Request → ExecutionContext
        Metadata Provider
        Service 调用
        Result → Response
        Exception Boundary
        """

        context = (
            ReviewExecutionContext
            .from_review_request(
                request
            )
        )

        context.metadata_provider = (
            self._resolve_metadata_provider(
                context
            )
        )

        if self.optimize_service is None:
            return (
                SQLOptimizeResponse.failed(
                    file_path=request.file_path,
                    trace_id=context.trace_id,
                    error_message=(
                        "Optimize service "
                        "is not configured."
                    ),
                )
            )

        try:
            result = (
                self.optimize_service
                .optimize(
                    context,
                    optimization_goals=(
                        request
                        .optimization_goals
                    ),
                    explain_response=(
                        explain_response
                    ),
                )
            )

            return (
                SQLOptimizeResponse
                .from_optimization_result(
                    result=result,
                    file_path=(
                        request.file_path
                    ),
                    trace_id=(
                        context.trace_id
                    ),
                )
            )

        except Exception as error:
            return (
                SQLOptimizeResponse.failed(
                    file_path=request.file_path,
                    trace_id=context.trace_id,
                    error_message=str(
                        error
                    ),
                )
            )

    def _resolve_metadata_provider(self, context: ReviewExecutionContext):
        if context.metadata_provider is not None:
            return context.metadata_provider
        if not context.enable_metadata:
            return None
        return self.metadata_provider_factory()

