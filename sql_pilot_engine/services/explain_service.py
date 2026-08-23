from __future__ import annotations

from sql_pilot_engine.core.execution_context import (
    SQLExecutionContext,
)
from sql_pilot_engine.llm.explainer import (
    LLMExplainer,
)
from sql_pilot_engine.schemas.responses import (
    SQLExplainResponse,
)


class ExplainService:

    def __init__(
        self,
        explainer: LLMExplainer,
    ) -> None:
        self.explainer = explainer

    def explain(
        self,
        context: SQLExecutionContext,
    ) -> SQLExplainResponse:

        try:
            payload = (
                self.explainer.explain(
                    sql=context.sql
                )
            )

            return (
                SQLExplainResponse
                .from_llm_payload(
                    payload=payload,
                    file_path=(
                        context.file_path
                    ),
                    trace_id=(
                        context.trace_id
                    ),
                )
            )

        except Exception as error:
            return (
                SQLExplainResponse.failed(
                    file_path=(
                        context.file_path
                    ),
                    trace_id=(
                        context.trace_id
                    ),
                    error_message=str(
                        error
                    ),
                )
            )