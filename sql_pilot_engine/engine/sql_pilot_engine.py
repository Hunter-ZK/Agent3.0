from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.core.models import ReviewResult
from sql_pilot_engine.metadata import MetadataProvider
from sql_pilot_engine.schemas.requests import (
    SQLExplainRequest,
    SQLFixRequest,
    SQLOptimizeRequest,
    SQLReviewRequest,
)
from sql_pilot_engine.schemas.responses import (
    SQLCriticResponse,
    SQLExplainResponse,
    SQLFixResponse,
    SQLOptimizeResponse,
    SQLReviewResponse,
)
from sql_pilot_engine.services.critic_service import CriticService
from sql_pilot_engine.services.explain_service import ExplainService
from sql_pilot_engine.services.fix_service import FixService
from sql_pilot_engine.services.optimize_service import OptimizeService
from sql_pilot_engine.services.review_service import ReviewService


class SQLPilotEngine:
    """
    SQLPilot 稳定 Engine 门面。

    Review / Fix / Explain / Optimize 共享统一的 Request -> ExecutionContext
    和 Metadata Provider 注入规则。
    """

    def __init__(
        self,
        review_service: ReviewService,
        fix_service: FixService | None = None,
        metadata_provider_factory: Callable[[], MetadataProvider] | None = None,
        explain_service: ExplainService | None = None,
        optimize_service: OptimizeService | None = None,
        critic_service: CriticService | None = None,
    ) -> None:
        self.explain_service = explain_service
        self.review_service = review_service or ReviewService()
        self.fix_service = fix_service or FixService(
            review_service=self.review_service
        )
        self.critic_service = critic_service or CriticService()
        self.optimize_service = optimize_service

        if (
            metadata_provider_factory is not None
            and not callable(metadata_provider_factory)
        ):
            raise TypeError(
                "metadata_provider_factory must be callable or None, got "
                f"{type(metadata_provider_factory).__name__}"
            )
        self.metadata_provider_factory = metadata_provider_factory

    @property
    def explain_available(self) -> bool:
        return self.explain_service is not None

    @property
    def optimize_available(self) -> bool:
        return self.optimize_service is not None

    @staticmethod
    def _extract_prior_review_result(
        *,
        prior_review: SQLReviewResponse | None,
        sql: str,
    ) -> ReviewResult | None:
        if prior_review is None or not prior_review.success:
            return None

        result = prior_review.raw_result
        if result is None or not result.reviewed_sql:
            return None
        if result.reviewed_sql != sql:
            raise ValueError(
                "prior_review does not belong to the SQL being fixed."
            )
        return result

    def review(
        self,
        request: SQLReviewRequest,
    ) -> SQLReviewResponse:
        context = self._build_execution_context(request)
        try:
            context.metadata_provider = self._resolve_metadata_provider(
                enable_metadata=context.enable_metadata,
                explicit_provider=context.metadata_provider,
            )
            result = self.review_service.review(context)
            return SQLReviewResponse.from_review_result(
                result,
                trace_id=context.trace_id,
            )
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
        context = self._build_execution_context(
            request,
            fix_sql=True,
            fix_provider=request.fix_provider,
            critic_feedback=request.critic_feedback,
            retry_count=request.retry_count,
        )
        try:
            context.metadata_provider = self._resolve_metadata_provider(
                enable_metadata=context.enable_metadata,
                explicit_provider=context.metadata_provider,
            )
            review_result = self._extract_prior_review_result(
                prior_review=prior_review,
                sql=request.sql,
            )
            result = self.fix_service.fix(
                context,
                review_result=review_result,
            )
            return SQLFixResponse.from_review_result(
                result,
                trace_id=context.trace_id,
            )
        except Exception as error:
            return SQLFixResponse.failed(
                task_type="fix",
                file_path=request.file_path,
                error_message=str(error),
                trace_id=context.trace_id,
            )

    def explain(
        self,
        request: SQLExplainRequest,
    ) -> SQLExplainResponse:
        context = self._build_execution_context(request)

        if self.explain_service is None:
            return SQLExplainResponse.failed(
                file_path=request.file_path,
                trace_id=context.trace_id,
                error_message="Explain service is not configured.",
            )

        try:
            context.metadata_provider = self._resolve_metadata_provider(
                enable_metadata=context.enable_metadata,
                explicit_provider=context.metadata_provider,
            )
            return self.explain_service.explain(context)
        except Exception as error:
            return SQLExplainResponse.failed(
                file_path=request.file_path,
                trace_id=context.trace_id,
                error_message=str(error),
            )

    def critique(
        self,
        *,
        review_response: SQLReviewResponse,
        fix_response: SQLFixResponse,
        re_review_response: SQLReviewResponse | None = None,
        trace_id: str | None = None,
    ) -> SQLCriticResponse:
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
        explain_response: SQLExplainResponse | None = None,
    ) -> SQLOptimizeResponse:
        context = self._build_execution_context(request)

        if self.optimize_service is None:
            return SQLOptimizeResponse.failed(
                file_path=request.file_path,
                trace_id=context.trace_id,
                error_message="Optimize service is not configured.",
            )

        try:
            context.metadata_provider = self._resolve_metadata_provider(
                enable_metadata=context.enable_metadata,
                explicit_provider=context.metadata_provider,
            )
            result = self.optimize_service.optimize(
                context,
                optimization_goals=request.optimization_goals,
                explain_response=explain_response,
            )
            return SQLOptimizeResponse.from_optimization_result(
                result=result,
                file_path=request.file_path,
                trace_id=context.trace_id,
            )
        except Exception as error:
            return SQLOptimizeResponse.failed(
                file_path=request.file_path,
                trace_id=context.trace_id,
                error_message=str(error),
            )

    def _resolve_metadata_provider(
        self,
        *,
        enable_metadata: bool,
        explicit_provider: MetadataProvider | None = None,
    ) -> MetadataProvider | None:
        if not enable_metadata:
            return None

        if explicit_provider is not None:
            return explicit_provider

        if self.metadata_provider_factory is None:
            raise RuntimeError(
                "Metadata validation is enabled but no metadata provider "
                "or metadata_provider_factory is configured."
            )

        return self.metadata_provider_factory()

    @staticmethod
    def _build_execution_context(
        request: SQLReviewRequest,
        *,
        fix_sql: bool = False,
        fix_provider: str = "auto",
        critic_feedback: list[str] | None = None,
        retry_count: int = 0,
    ) -> SQLExecutionContext:
        return SQLExecutionContext(
            sql=request.sql,
            file_path=request.file_path,
            mode=request.mode,
            dialect=request.dialect,
            categories=request.categories,
            enable_metadata=request.enable_metadata,
            metadata_provider=request.metadata_provider,
            trust_evidence=request.trust_evidence,
            enable_llm=request.enable_llm,
            llm_provider=request.llm_provider,
            query_context=request.query_context,
            rule_packs=request.rule_packs,
            fix_sql=fix_sql,
            fix_provider=fix_provider,
            trace_id=request.trace_id or str(uuid4()),
            critic_feedback=list(critic_feedback or []),
            retry_count=retry_count,
        )
