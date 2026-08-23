from __future__ import annotations

from sql_pilot_engine.llm.clients import (
    BaseLLMClient,
)
from sql_pilot_engine.optimization.context import (
    SQLOptimizationContext,
)
from sql_pilot_engine.optimization.models import (
    OptimizationProposal,
    OptimizationSuggestion,
)
from sql_pilot_engine.optimization.prompts import (
    build_sql_optimization_prompt,
)


class SQLOptimizeAgent:
    """
    LLM-first SQL Optimization Agent。

    责任：
    1. 消费 Optimization Context；
    2. 构造 Prompt；
    3. 调用 LLM；
    4. 解析结构化 Optimization Proposal。

    不负责：
    - Trusted SQL Review
    - 最终采纳 Candidate
    - Semantic Equivalence 验证
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
    ) -> None:
        self.llm_client = llm_client

    def optimize(
        self,
        context: SQLOptimizationContext,
    ) -> OptimizationProposal:

        (
            system_prompt,
            user_prompt,
            json_schema,
        ) = build_sql_optimization_prompt(
            context
        )

        payload = (
            self.llm_client.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=json_schema,
            )
        )

        suggestions = tuple(
            self._build_suggestion(item)
            for item in (
                payload.get(
                    "suggestions"
                )
                or []
            )
            if isinstance(
                item,
                dict,
            )
        )

        candidate_sql = (
            payload.get(
                "candidate_sql"
            )
        )

        if isinstance(
            candidate_sql,
            str,
        ):
            candidate_sql = (
                candidate_sql.strip()
                or None
            )

        confidence = (
            payload.get(
                "confidence",
                0.0,
            )
        )

        try:
            confidence = float(
                confidence
            )
        except (
            TypeError,
            ValueError,
        ):
            confidence = 0.0

        confidence = max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

        return OptimizationProposal(
            summary=str(
                payload.get(
                    "summary",
                    "",
                )
            ),
            suggestions=suggestions,
            candidate_sql=(
                candidate_sql
            ),
            rewrite_reason=(
                payload.get(
                    "rewrite_reason"
                )
            ),
            assumptions=tuple(
                str(item)
                for item in (
                    payload.get(
                        "assumptions"
                    )
                    or []
                )
            ),
            confidence=confidence,
            raw_output=payload,
        )

    @staticmethod
    def _build_suggestion(
        item: dict,
    ) -> OptimizationSuggestion:

        return OptimizationSuggestion(
            category=str(
                item.get(
                    "category",
                    "other",
                )
            ),
            priority=str(
                item.get(
                    "priority",
                    "medium",
                )
            ),
            description=str(
                item.get(
                    "description",
                    "",
                )
            ),
            reason=str(
                item.get(
                    "reason",
                    "",
                )
            ),
            expected_benefit=str(
                item.get(
                    "expected_benefit",
                    "",
                )
            ),
            risk=str(
                item.get(
                    "risk",
                    "",
                )
            ),
            requires_execution_validation=bool(
                item.get(
                    "requires_execution_validation",
                    False,
                )
            ),
        )