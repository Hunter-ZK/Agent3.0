from __future__ import annotations

from typing import Any

from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
)
from sql_pilot_engine.llm.errors import (
    LLMResponseValidationError,
)
from sql_pilot_engine.llm.optimize_prompts import (
    OPTIMIZE_JSON_SCHEMA,
    OPTIMIZE_SYSTEM_PROMPT,
    build_optimize_user_prompt,
)
from sql_pilot_engine.optimization.models import (
    OptimizationResult,
    OptimizationSuggestion,
)


class LLMOptimizer:
    """
    LLM SQL Optimization 执行器。

    只负责：
    Prompt → LLM → OptimizationResult

    不负责：
    - Candidate Review
    - Candidate 是否被最终采用
    """

    def __init__(
        self,
        client: StructuredGenerationModel,
    ) -> None:
        self.client = client

    def optimize(
        self,
        *,
        sql: str,
        dialect: str,
        optimization_goals: list[str],
        analysis_context_text: str,
        metadata_context_text: str,
        explain_context_text: str,
    ) -> OptimizationResult:

        user_prompt = (
            build_optimize_user_prompt(
                sql=sql,
                dialect=dialect,
                optimization_goals=(
                    optimization_goals
                ),
                analysis_context_text=(
                    analysis_context_text
                ),
                metadata_context_text=(
                    metadata_context_text
                ),
                explain_context_text=(
                    explain_context_text
                ),
            )
        )

        raw_result = (
            self.client.generate_json(
                system_prompt=(
                    OPTIMIZE_SYSTEM_PROMPT
                ),
                user_prompt=user_prompt,
                json_schema=(
                    OPTIMIZE_JSON_SCHEMA
                ),
            )
        )

        return self._parse_result(
            sql=sql,
            raw_result=raw_result,
        )

    def _parse_result(
        self,
        *,
        sql: str,
        raw_result: dict[
            str,
            Any,
        ],
    ) -> OptimizationResult:

        if not isinstance(
            raw_result,
            dict,
        ):
            raise (
                LLMResponseValidationError(
                    "LLM Optimize 返回结果"
                    "必须是 JSON object。"
                )
            )

        required_fields = {
            "summary",
            "suggestions",
            "candidate_sql",
            "rewrite_reason",
            "assumptions",
            "confidence",
        }

        missing_fields = (
            required_fields
            - set(
                raw_result.keys()
            )
        )

        if missing_fields:
            raise (
                LLMResponseValidationError(
                    "LLM Optimize 返回结果"
                    "缺少字段："
                    f"{sorted(missing_fields)}"
                )
            )

        suggestions_value = (
            raw_result["suggestions"]
        )

        if not isinstance(
            suggestions_value,
            list,
        ):
            raise (
                LLMResponseValidationError(
                    "suggestions 必须是数组。"
                )
            )

        suggestions = tuple(
            self._parse_suggestion(
                item
            )
            for item in suggestions_value
        )

        candidate_sql = (
            raw_result["candidate_sql"]
        )

        if candidate_sql is not None:
            if not isinstance(
                candidate_sql,
                str,
            ):
                raise (
                    LLMResponseValidationError(
                        "candidate_sql "
                        "必须是字符串或 null。"
                    )
                )

            candidate_sql = (
                candidate_sql.strip()
                or None
            )

        assumptions = (
            raw_result["assumptions"]
        )

        if not isinstance(
            assumptions,
            list,
        ):
            raise (
                LLMResponseValidationError(
                    "assumptions 必须是数组。"
                )
            )

        try:
            confidence = float(
                raw_result["confidence"]
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise (
                LLMResponseValidationError(
                    "confidence 必须是数字。"
                )
            ) from error

        if not 0 <= confidence <= 1:
            raise (
                LLMResponseValidationError(
                    "confidence 必须在 "
                    "0 到 1 之间。"
                )
            )

        rewrite_reason = (
            raw_result[
                "rewrite_reason"
            ]
        )

        if (
            rewrite_reason is not None
            and not isinstance(
                rewrite_reason,
                str,
            )
        ):
            raise (
                LLMResponseValidationError(
                    "rewrite_reason "
                    "必须是字符串或 null。"
                )
            )

        return OptimizationResult(
            original_sql=sql,
            summary=str(
                raw_result["summary"]
            ),
            suggestions=suggestions,
            candidate_sql=candidate_sql,
            rewrite_reason=(
                rewrite_reason
            ),
            assumptions=tuple(
                str(item)
                for item
                in assumptions
            ),
            confidence=confidence,
            raw_output=raw_result,
        )

    @staticmethod
    def _parse_suggestion(
        item: Any,
    ) -> OptimizationSuggestion:

        if not isinstance(
            item,
            dict,
        ):
            raise (
                LLMResponseValidationError(
                    "Optimization suggestion "
                    "必须是 object。"
                )
            )

        required = {
            "category",
            "priority",
            "description",
            "reason",
            "expected_benefit",
            "risk",
            "requires_execution_validation",
        }

        missing = (
            required
            - set(
                item.keys()
            )
        )

        if missing:
            raise (
                LLMResponseValidationError(
                    "Optimization suggestion "
                    "缺少字段："
                    f"{sorted(missing)}"
                )
            )

        priority = str(
            item["priority"]
        ).lower()

        if priority not in {
            "low",
            "medium",
            "high",
        }:
            raise (
                LLMResponseValidationError(
                    "priority 必须是 "
                    "low、medium 或 high。"
                )
            )

        return OptimizationSuggestion(
            category=str(
                item["category"]
            ),
            priority=priority,
            description=str(
                item["description"]
            ),
            reason=str(
                item["reason"]
            ),
            expected_benefit=str(
                item[
                    "expected_benefit"
                ]
            ),
            risk=str(
                item["risk"]
            ),
            requires_execution_validation=bool(
                item[
                    "requires_execution_validation"
                ]
            ),
        )