from __future__ import annotations

from sql_pilot_engine.core.execution_context import (
    SQLExecutionContext,
)
from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
)
from sql_pilot_engine.schemas.responses import (
    SQLExplainResponse,
)
from sql_pilot_engine.llm.explainer import (
    LLMExplainer,
)

class ExplainService:

    def __init__(
        self,
        llm_client: StructuredGenerationModel,
    ) -> None:
        self._explainer = LLMExplainer(client=llm_client)

    def explain(
        self,
        context: SQLExecutionContext,
    ) -> SQLExplainResponse:

        try:
            payload = (
                self._explainer.explain(
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