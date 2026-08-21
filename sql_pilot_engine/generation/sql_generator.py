from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.generation.llm import (
    TextGenerationModel,
)

from sql_pilot_engine.generation.models import (
    GeneratedSQL,
    QueryPlan,
)

from sql_pilot_engine.generation.prompts import (
    build_sql_prompt,
)


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
        query_context: QueryContext,
        dialect: str="maxcompute",
        revision_feedback: tuple[str, ...] = (),
    ) -> GeneratedSQL:
        
        prompt = build_sql_prompt(
            plan=plan,
            query_context=query_context,
            dialect=dialect,
            revision_feedback=revision_feedback,
        )

        logger.debug(
            "generator.prompt\n%s",
            prompt,
        )
                
        sql = (
            self.model.generate(prompt).strip()
        )
        
        logger.debug(
            "generator.response\n%s",
            sql,
        )
        
        return GeneratedSQL(
            sql=sql,
            dialect=dialect,
        )