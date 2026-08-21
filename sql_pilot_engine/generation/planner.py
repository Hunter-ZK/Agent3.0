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
        query_context: QueryContext,
    ) -> QueryPlanningOutcome:
        
        prompt = build_planner_prompt(
            question=question,
            semantic_context=query_context.semantic_context,
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

        # ========================================================
        # 1. Context不足：向用户追问
        # ========================================================

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

        # ========================================================
        # 2. 新版Planner契约：
        #
        # {
        #   "status": "ready",
        #   "plan": {...}
        # }
        # ========================================================

        if status == "ready":
            plan_data = data["plan"]

        # ========================================================
        # 3. 向后兼容旧Fake Model：
        #
        # {
        #   "tables": [...],
        #   ...
        # }
        # ========================================================
        else:
            plan_data = data
            
        # ========================================================
        # 4. 一定从plan_data读取
        # ========================================================
        return QueryPlan(
            tables=tuple(
                plan_data.get(
                    "tables",
                    []
                )
            ),
            dimensions=tuple(
                plan_data.get(
                    "dimensions",
                    []
                )
            ),
            metrics=tuple(
                plan_data.get(
                    "metrics",
                    []
                )
            ),
            filters=tuple(
                plan_data.get(
                    "filters",
                    []
                )
            ),
            group_by=tuple(
                plan_data.get(
                    "group_by",
                    []
                )
            ),
            requirements=tuple(
                plan_data.get(
                    "requirements",
                    [],
                )
            )
        )