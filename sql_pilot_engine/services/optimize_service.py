from __future__ import annotations

import json

from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
)
from sql_pilot_engine.core.execution_context import (
    ReviewExecutionContext,
)
from sql_pilot_engine.llm.clients import (
    BaseLLMClient,
)
from sql_pilot_engine.llm.context_builder import (
    build_analysis_context_text,
    build_metadata_context_text,
)
from sql_pilot_engine.llm.optimizer import (
    LLMOptimizer,
)
from sql_pilot_engine.optimization.models import (
    OptimizationResult,
)
from sql_pilot_engine.schemas.responses import (
    SQLExplainResponse,
)


class OptimizeService:
    """
    SQL Optimization 内部主服务。

    负责：
    1. 对 Trusted SQL 做一次结构分析；
    2. 构建 Analysis / Metadata / Explain Context；
    3. 调用 LLMOptimizer；
    4. 返回 OptimizationResult。

    不负责：
    - 决定 candidate_sql 是否可信；
    - 最终采用 candidate_sql；
    - Workflow Routing。
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        analysis_adapter: (
            SQLAnalysisAdapter | None
        ) = None,
    ) -> None:
        self.llm_client = llm_client

        self.analysis_adapter = (
            analysis_adapter
            or SQLAnalysisAdapter()
        )

    def optimize(
        self,
        context: ReviewExecutionContext,
        *,
        optimization_goals: list[str],
        explain_response: (
            SQLExplainResponse | None
        ) = None,
    ) -> OptimizationResult:

        analysis = (
            self.analysis_adapter.analyze(
                sql=context.sql,
                dialect=context.dialect,
            )
        )

        if not analysis.parse_result.success:
            raise ValueError(
                "Trusted SQL cannot be parsed "
                "during optimization."
            )

        facts = analysis.facts

        if facts is None:
            raise RuntimeError(
                "Successful optimization analysis "
                "must contain SQLFacts."
            )

        analysis_context_text = (
            build_analysis_context_text(
                facts=facts,
                dialect=context.dialect,
            )
        )

        metadata_context_text = (
            build_metadata_context_text(
                facts=facts,
                metadata_provider=(
                    context.metadata_provider
                ),
            )
        )

        explain_context_text = (
            self._build_explain_context_text(
                explain_response
            )
        )

        optimizer = LLMOptimizer(
            client=self.llm_client
        )

        return optimizer.optimize(
            sql=context.sql,
            dialect=context.dialect,
            optimization_goals=(
                optimization_goals
            ),
            analysis_context_text=(
                analysis_context_text
            ),
            metadata_context_text=(
                metadata_context_text
            ),
            explain_context_text=(
                explain_context_text
            ),
        )

    @staticmethod
    def _build_explain_context_text(
        explain_response: (
            SQLExplainResponse | None
        ),
    ) -> str:

        if (
            explain_response is None
            or not explain_response.success
        ):
            return "无可用 Explain Context。"

        payload = {
            "sql_summary": (
                explain_response.sql_summary
            ),
            "business_purpose": (
                explain_response
                .business_purpose
            ),
            "main_tables": (
                explain_response.main_tables
            ),
            "output_columns": (
                explain_response
                .output_columns
            ),
            "cte_steps": (
                explain_response.cte_steps
            ),
            "cte_dependencies": (
                explain_response
                .cte_dependencies
            ),
            "suspicious_points": (
                explain_response
                .suspicious_points
            ),
            "uncertainties": (
                explain_response
                .uncertainties
            ),
        }

        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )