from __future__ import annotations

import logging

from dataclasses import dataclass
from enum import Enum
from typing import Any

from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.llm.protocols import (
    TextGenerationModel,
    StructuredGenerationModel,
)
from sql_pilot_engine.llm.errors import (
    LLMResponseValidationError,
)
from sql_pilot_engine.generation.models import (
    QueryPlan,
)
from sql_pilot_engine.context.query_context_renderer import (
    render_query_context,
)

logger = logging.getLogger(__name__)


SEMANTIC_VALIDATION_JSON_SCHEMA = {
    "name": "semantic_validation_result",

    "schema": {
        "type": "object",

        "properties": {
            "status": {
                "type": "string",

                "enum": [
                    "pass",
                    "fail",
                    "need_clarification",
                ],
            },

            "missing_requirements": {
                "type": "array",

                "items": {
                    "type": "string",
                },
            },

            "issues": {
                "type": "array",

                "items": {
                    "type": "string",
                },
            },
        },

        "required": [
            "status",
            "missing_requirements",
            "issues",
        ],

        "additionalProperties": False,
    },
}


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
        model: StructuredGenerationModel,
    ) -> None:
        
        self._model = model
    
    def validate(
        self,
        *,
        sql: str,
        plan: QueryPlan,
        query_context: QueryContext,
    ) -> SemanticValidationResult:
        
        user_prompt = self._build_prompt(
            sql=sql,
            plan=plan,
            query_context=query_context,
        )
        
        logger.debug(
            "semantic_validation.prompt\n%s",
            user_prompt,
        )
        
        raw = self._model.generate_json(
            system_prompt=(
                self._system_prompt()
            ),
            user_prompt=user_prompt,
            json_schema=(
                SEMANTIC_VALIDATION_JSON_SCHEMA
            ),
        )
        
        logger.debug(
            "semantic_validation.response\n%s",
            raw,
        )
            
        return self._parse_result(raw)
        
    @staticmethod
    def _system_prompt() -> str:

        return """
    You are Agent3.0's semantic SQL validator.

    Your task is to determine whether an SQL query
    fully satisfies the user's business request
    according to the supplied Task Context
    and Query Plan.

    Do NOT perform basic syntax or safety review.
    Those stages have already completed.

    Do NOT invent business definitions,
    metric formulas, filters, time rules,
    physical fields or user intent.

    Use need_clarification only when information
    that materially changes the business answer
    is genuinely missing and can be answered
    by the user.

    Return only the structured result required
    by the supplied JSON Schema.
    """.strip()   
        
    @staticmethod
    def _build_prompt(
        *,
        sql: str,
        plan: QueryPlan,
        query_context: QueryContext,
    ) -> str:
        
        context_text = (
            render_query_context(
                query_context
            )
        )
        
        return f"""
Task Context:

{context_text}


Query Plan:

tables={plan.tables}
dimensions={plan.dimensions}
metrics={plan.metrics}
filters={plan.filters}
group_by={plan.group_by}
requirements={plan.requirements}


SQL to evaluate:

{sql}


Check whether the SQL:

1. answers every material requirement;
2. uses the intended business subject;
3. implements the intended metric;
4. applies required business filters;
5. respects relevant time semantics;
6. respects the required aggregation grain;
7. does not silently omit material requirements.

If SQL is semantically correct:
status = pass

If SQL is wrong but the supplied context is sufficient
to explain what is wrong:
status = fail

If materially different correct SQL would depend on
missing user/business information:
status = need_clarification
""".strip()


    @staticmethod
    def _parse_result(
        data: dict[str, Any],
    ) -> SemanticValidationResult:

        if not isinstance(
            data,
            dict,
        ):
            raise LLMResponseValidationError(
                "Semantic validation "
                "result must be an object."
            )

        raw_status = data.get(
            "status"
        )

        try:
            status = (
                SemanticValidationStatus(
                    raw_status
                )
            )

        except (
            TypeError,
            ValueError,
        ) as error:

            raise LLMResponseValidationError(
                "Invalid semantic "
                "validation status: "
                f"{raw_status!r}"
            ) from error

        missing_requirements = (
            data.get(
                "missing_requirements"
            )
        )

        issues = data.get(
            "issues"
        )

        if not isinstance(
            missing_requirements,
            list,
        ):
            raise LLMResponseValidationError(
                "missing_requirements "
                "must be an array."
            )

        if not isinstance(
            issues,
            list,
        ):
            raise LLMResponseValidationError(
                "issues must be an array."
            )

        if not all(
            isinstance(item, str)
            for item
            in missing_requirements
        ):
            raise LLMResponseValidationError(
                "missing_requirements "
                "items must be strings."
            )

        if not all(
            isinstance(item, str)
            for item
            in issues
        ):
            raise LLMResponseValidationError(
                "issues items "
                "must be strings."
            )

        normalized_missing = tuple(
            item.strip()
            for item
            in missing_requirements
            if item.strip()
        )

        normalized_issues = tuple(
            item.strip()
            for item
            in issues
            if item.strip()
        )

        if (
            status
            is SemanticValidationStatus
            .NEED_CLARIFICATION
            and not normalized_missing
        ):
            raise LLMResponseValidationError(
                "need_clarification "
                "requires missing_requirements."
            )

        return SemanticValidationResult(
            status=status,

            missing_requirements=(
                normalized_missing
            ),

            issues=(
                normalized_issues
            ),
        )