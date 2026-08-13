from __future__ import annotations

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
        question: str,
        plan: QueryPlan,
        semantic_context: str,
        query_context: QueryContext,
        dialect: str="maxcompute",
    ) -> GeneratedSQL:
        
        prompt = build_sql_prompt(
            question=question,
            plan=plan,
            semantic_context=semantic_context,
            query_context=query_context,
            dialect=dialect,
        )
        
        sql = (
            self.model.generate(prompt).strip()
        )
        
        return GeneratedSQL(
            sql=sql,
            dialect=dialect,
        )