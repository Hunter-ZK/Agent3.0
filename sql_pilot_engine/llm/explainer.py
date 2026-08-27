from __future__ import annotations

from typing import Any

from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
)
from sql_pilot_engine.llm.explain_prompts import (
    EXPLAIN_JSON_SCHEMA,
    EXPLAIN_SYSTEM_PROMPT,
    build_explain_user_prompt,
)

class LLMExplainer:

    def __init__(
        self,
        client: StructuredGenerationModel,
    ) -> None:
        self.client = client

    def explain(
        self,
        *,
        sql: str,
    ) -> dict[str, Any]:

        return self.client.generate_json(
            system_prompt=(
                EXPLAIN_SYSTEM_PROMPT
            ),
            user_prompt=(
                build_explain_user_prompt(
                    sql
                )
            ),
            json_schema=(
                EXPLAIN_JSON_SCHEMA
            ),
        )
