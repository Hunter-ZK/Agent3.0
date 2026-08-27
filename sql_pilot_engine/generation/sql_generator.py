from __future__ import annotations

import logging

from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.llm.protocols import (
    TextGenerationModel,
)

from sql_pilot_engine.generation.models import (
    GeneratedSQL,
    QueryPlan,
)

from sql_pilot_engine.generation.prompts import (
    build_sql_prompt,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
)

logger = logging.getLogger(__name__)


class SQLGenerator:

    def __init__(
        self,
        model: TextGenerationModel,
    ) -> None:

        self.model = model

    def generate(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        query_context: QueryContext,
        dialect: str = "maxcompute",
        revision_feedback: tuple[
            str,
            ...
        ] = (),
    ) -> GeneratedSQL:

        if not linked_schema.resolved:
            raise ValueError(
                "SQLGenerator cannot use "
                "an unresolved LinkedSchema."
            )

        prompt = build_sql_prompt(
            plan=plan,
            linked_schema=linked_schema,
            query_context=query_context,
            dialect=dialect,
            revision_feedback=(
                revision_feedback
            ),
        )

        logger.debug(
            "generator.prompt\n%s",
            prompt,
        )

        raw_sql = (
            self.model.generate(
                prompt
            )
        )

        sql = (
            self._normalize_sql_output(
                raw_sql
            )
        )

        logger.debug(
            "generator.response\n%s",
            sql,
        )

        return GeneratedSQL(
            sql=sql,
            dialect=dialect,
        )

    @staticmethod
    def _normalize_sql_output(
        raw: str,
    ) -> str:

        text = raw.strip()

        lines = text.splitlines()

        if len(lines) < 2:
            return text

        first_line = (
            lines[0]
            .strip()
            .lower()
        )

        last_line = (
            lines[-1]
            .strip()
        )

        if (
            first_line
            in {
                "```sql",
                "```",
            }
            and last_line == "```"
        ):
            return (
                "\n".join(
                    lines[1:-1]
                )
                .strip()
            )

        return text