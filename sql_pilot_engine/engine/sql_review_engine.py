# sql_review_agent/engine/sql_review_engine.py

from collections.abc import Callable
from typing import Any

from sql_pilot_engine.metadata.provider import MockMetadataProvider
from sql_pilot_engine.schemas.requests import SQLExplainRequest, SQLFixRequest, SQLOptimizeRequest, SQLReviewRequest
from sql_pilot_engine.schemas.responses import SQLFixResponse, SQLReviewResponse, SQLExplainResponse
from sql_pilot_engine.services.review_service import ReviewService
from sql_pilot_engine.core.execution_context import ReviewExecutionContext
from sql_pilot_engine.agents.sql_explain_agent import SQLExplainAgent
from sql_pilot_engine.services.critic_service import CriticService, SQLCriticResponse
from sql_pilot_engine.services.fix_service import FixService


class SQLPilotEngine:
    """SQLPilot 的稳定 Engine 门面。

    Engine 是外部入口，ReviewService 是内部编排服务。后续 CLI、FastAPI、
    Streamlit、Agent Workflow 都应该优先调用 Engine，而不是直接调用 ReviewService。
    """

    def __init__(
        self,
        review_service: ReviewService | None = None,
        fix_service: FixService | None = None,
        metadata_provider_factory: Callable[[], Any] | None = None,
        explain_agent: SQLExplainAgent | None = None,
        critic_service: CriticService | None = None,
    ) -> None:
        self.review_service = review_service or ReviewService()
        self.fix_service = fix_service
        self.metadata_provider_factory = metadata_provider_factory or MockMetadataProvider
        self.explain_agent = explain_agent
        self.critic_service = critic_service or CriticService()

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

    def fix(self, request: SQLFixRequest) -> SQLFixResponse:
        """先审查 SQL，再生成完整修复 SQL。"""
        context = ReviewExecutionContext.from_fix_request(request)
        context.metadata_provider = self._resolve_metadata_provider(context)
        try:
            result = self.fix_service.fix(context)
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
    

    def critique(self,
                 *,
                 review_response: SQLReviewResponse,
                 fix_reponse: SQLFixResponse,
                 re_review_response: SQLReviewResponse,
                 trace_id: str | None = None,):
        return self.critic_service.critique(
            review_response=review_response,
            fix_response=fix_reponse,
            re_review_response=re_review_response,
            trace_id=trace_id,
        )

    def optimize(self, request: SQLOptimizeRequest) -> SQLReviewResponse:
        """Optimize 占位：C/D 阶段接入 LLM 与 RAG 后实现。"""
        return SQLReviewResponse.failed(
            task_type="optimize",
            file_path=request.file_path,
            error_message="SQLOptimizeRequest is not implemented in Phase B.",
        )

    def _resolve_metadata_provider(self, context: ReviewExecutionContext):
        if context.metadata_provider is not None:
            return context.metadata_provider
        if not context.enable_metadata:
            return None
        return self.metadata_provider_factory()

