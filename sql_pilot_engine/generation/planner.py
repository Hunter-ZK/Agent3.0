from __future__ import annotations

import json

import logging

logger = logging.getLogger(__name__)

from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.generation.llm import (
    TextGenerationModel,
)


from sql_pilot_engine.generation.models import (
    QueryPlan,
    PlanningClarification,
    QueryPlanningOutcome,
)

from sql_pilot_engine.generation.prompts import (
    build_planner_prompt,
)



class QueryPlanner:
    
    def __init__(
        self,
        model: TextGenerationModel,
    ) -> None:
        self.model = model
        
    
    def plan(
        self,
        *,
        question: str,
        semantic_context: str,
        query_context: QueryContext,
    ) -> QueryPlanningOutcome:
        
        prompt = build_planner_prompt(
            question=question,
            semantic_context=semantic_context,
            query_context=query_context,
        )
        
        logger.debug(
            "planner.prompt\n%s",
            prompt,
        )
        
        raw = self.model.generate(
            prompt=prompt
        )
        
        logger.debug(
            "planner.response\n%s",
            raw,
        )
        
        data = json.loads(raw)

        status = data.get("status")

        if status == "need_clarification":
            return PlanningClarification(
                clarification_question=(
                    data["clarification_question"]
                ),
                missing_context=tuple(
                    data.get("missing_context",[],)
                ),
                reason=data.get("reason","",),
            )

        if status == "ready":
            plan_data = data["plan"]
            
        return QueryPlan(
            tables=tuple(
                data.get(
                    "tables",
                    []
                )
            ),
            dimensions=tuple(
                data.get(
                    "dimensions",
                    []
                )
            ),
            metrics=tuple(
                data.get(
                    "metrics",
                    []
                )
            ),
            filters=tuple(
                data.get(
                    "filters",
                    []
                )
            ),
            group_by=tuple(
                data.get(
                    "group_by",
                    []
                )
            ),
            requirements=tuple(
                data.get(
                    "requirements",
                    [],
                )
            )
        )