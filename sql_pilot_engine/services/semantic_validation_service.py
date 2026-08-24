from __future__ import annotations

import json
import logging

from dataclasses import dataclass
from enum import Enum

from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.generation.llm import (
    TextGenerationModel,
)
from sql_pilot_engine.generation.models import (
    QueryPlan,
)
from sql_pilot_engine.generation.prompts import (
    render_query_context,
)

logger = logging.getLogger(__name__)


class SemanticValidationStatus(
    str,
    Enum,
):
    PASS = "pass"
    FAIL = "fail"
    NEED_CLARIFICATION = (
        "need_clarification"
    )
    

@dataclass(frozen=True)
class SemanticValidationResult:
    
    status: SemanticValidationStatus
    
    missing_requirements: tuple[str, ...] = ()
    
    issues: tuple[str, ...] = ()
    
    @property
    def passed(self) -> bool:
        return (
            self.status is SemanticValidationStatus.PASS
        )
        
class SemanticSQLValidator:
    """判断SQL是否真正满足用户业务问题"""
    
    def __init__(
        self,
        *,
        model: TextGenerationModel,
    ) -> None:
        
        self._model = model
    
    def validate(
        self,
        *,
        sql: str,
        plan: QueryPlan,
        query_context: QueryContext,
    ) -> SemanticValidationResult:
        
        prompt = self._build_prompt(
            sql=sql,
            plan=plan,
            query_context=query_context,
        )
        
        logger.debug(
            "semantic_validation.prompt\n%s",
            prompt,
        )
        
        raw = self._model.generate(
            prompt=prompt
        )
        
        logger.debug(
            "semantic_validation.response\n%s",
            raw,
        )
        
        data = json.loads(raw)
        
        status = SemanticValidationStatus(
            data["status"]
        )
                
        
        return SemanticValidationResult(
            status=status,
            
            missing_requirements=tuple(
                data.get("missing_requirements",[],)
            ),
            
            issues=tuple(
                data.get("issues",[],)
            ),
        )
        
    @staticmethod
    def _build_prompt(
        *,
        sql: str,
        plan: QueryPlan,
        query_context: QueryContext,
    ) -> str:
        
        retrieved_context = (
            render_query_context(
                query_context
            )
        )
        
        return f"""
You are a semantic SQL validator.

Your task is NOT to check SQL syntax or SQL safety.
Those checks have already been performed.

Determine whether the SQL fully and correctly
answers the original user question according to
the available business context.

Original question:
{query_context.question}

Query plan:
tables={plan.tables}
dimensions={plan.dimensions}
metrics={plan.metrics}
filters={plan.filters}
group_by={plan.group_by}
requirements={plan.requirements}

Semantic model:
{query_context.semantic_context}

Retrieved business context:
{retrieved_context}

SQL to evaluate:
{sql}

Check whether the SQL:
1. answers every material requirement in the question;
2. uses the correct business subject/table;
3. uses the correct metric definition;
4. applies required business filters;
5. respects relevant time and aggregation rules;
6. does not silently omit analytical requirements.

If the question cannot be answered unambiguously
from the supplied context, return NEED_CLARIFICATION.

Return JSON only:

{{
  "status": "pass | fail | need_clarification",
  "missing_requirements": [],
  "issues": []
}}
""".strip()