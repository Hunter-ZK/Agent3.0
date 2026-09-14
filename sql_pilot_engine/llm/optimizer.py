from __future__ import annotations

from typing import Any

from sql_pilot_engine.llm.errors import (
    LLMResponseValidationError,
)
from sql_pilot_engine.llm.optimize_prompts import (
    OPTIMIZE_JSON_SCHEMA,
    OPTIMIZE_SYSTEM_PROMPT,
    PATCH_OPTIMIZE_JSON_SCHEMA,
    PATCH_OPTIMIZE_SYSTEM_PROMPT,
    build_optimize_user_prompt,
    build_patch_optimize_user_prompt,
)
from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
)
from sql_pilot_engine.optimization.models import (
    OptimizationResult,
    OptimizationSuggestion,
)


MAX_FULL_OPTIMIZE_REWRITE_CHARS = 16000


class LLMOptimizer:
    """
    LLM SQL Optimization 执行器。

    普通 SQL 可以返回完整 candidate_sql；
    超长 production program 自动切换 scoped patch，避免 one-shot 重写。
    """

    def __init__(
        self,
        client: StructuredGenerationModel,
        *,
        max_full_rewrite_chars: int = MAX_FULL_OPTIMIZE_REWRITE_CHARS,
    ) -> None:
        self.client = client
        self.max_full_rewrite_chars = max_full_rewrite_chars

    def optimize(
        self,
        *,
        sql: str,
        dialect: str,
        optimization_goals: list[str],
        analysis_context_text: str,
        metadata_context_text: str,
        explain_context_text: str,
        program_evidence_context_text: str = "",
    ) -> OptimizationResult:
        if len(sql) > self.max_full_rewrite_chars:
            return self._optimize_with_scoped_patches(
                sql=sql,
                dialect=dialect,
                optimization_goals=optimization_goals,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                explain_context_text=explain_context_text,
                program_evidence_context_text=(
                    program_evidence_context_text
                ),
            )

        raw_result = self.client.generate_json(
            system_prompt=OPTIMIZE_SYSTEM_PROMPT,
            user_prompt=build_optimize_user_prompt(
                sql=sql,
                dialect=dialect,
                optimization_goals=optimization_goals,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                explain_context_text=explain_context_text,
                program_evidence_context_text=(
                    program_evidence_context_text
                ),
            ),
            json_schema=OPTIMIZE_JSON_SCHEMA,
        )

        return self._parse_result(
            sql=sql,
            raw_result=raw_result,
        )

    def _optimize_with_scoped_patches(
        self,
        *,
        sql: str,
        dialect: str,
        optimization_goals: list[str],
        analysis_context_text: str,
        metadata_context_text: str,
        explain_context_text: str,
        program_evidence_context_text: str,
    ) -> OptimizationResult:
        raw_result = self.client.generate_json(
            system_prompt=PATCH_OPTIMIZE_SYSTEM_PROMPT,
            user_prompt=build_patch_optimize_user_prompt(
                sql=sql,
                dialect=dialect,
                optimization_goals=optimization_goals,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                explain_context_text=explain_context_text,
                program_evidence_context_text=(
                    program_evidence_context_text
                ),
            ),
            json_schema=PATCH_OPTIMIZE_JSON_SCHEMA,
        )

        if not isinstance(raw_result, dict):
            raise LLMResponseValidationError(
                "LLM Optimize Patch 返回结果必须是 JSON object。"
            )

        required_fields = {
            "summary",
            "suggestions",
            "patches",
            "rewrite_reason",
            "assumptions",
            "confidence",
        }
        missing = required_fields - set(raw_result)
        if missing:
            raise LLMResponseValidationError(
                f"LLM Optimize Patch 缺少字段：{sorted(missing)}"
            )

        suggestions_value = raw_result["suggestions"]
        if not isinstance(suggestions_value, list):
            raise LLMResponseValidationError(
                "suggestions 必须是数组。"
            )
        suggestions = tuple(
            self._parse_suggestion(item)
            for item in suggestions_value
        )

        patches = raw_result["patches"]
        if not isinstance(patches, list):
            raise LLMResponseValidationError(
                "patches 必须是数组。"
            )

        candidate_sql, patch_reasons = self._apply_patches(
            sql=sql,
            patches=patches,
        )

        assumptions = raw_result["assumptions"]
        if not isinstance(assumptions, list):
            raise LLMResponseValidationError(
                "assumptions 必须是数组。"
            )

        confidence = self._parse_confidence(
            raw_result["confidence"]
        )

        rewrite_reason = raw_result["rewrite_reason"]
        if rewrite_reason is not None and not isinstance(
            rewrite_reason,
            str,
        ):
            raise LLMResponseValidationError(
                "rewrite_reason 必须是字符串或 null。"
            )

        combined_reason = rewrite_reason
        if patch_reasons:
            patch_text = "; ".join(patch_reasons)
            combined_reason = (
                f"{rewrite_reason}; {patch_text}"
                if rewrite_reason
                else patch_text
            )

        return OptimizationResult(
            original_sql=sql,
            summary=str(raw_result["summary"]),
            suggestions=suggestions,
            candidate_sql=(
                candidate_sql
                if candidate_sql != sql
                else None
            ),
            rewrite_reason=combined_reason,
            assumptions=tuple(
                str(item) for item in assumptions
            ),
            confidence=confidence,
            raw_output=raw_result,
        )

    @staticmethod
    def _apply_patches(
        *,
        sql: str,
        patches: list[Any],
    ) -> tuple[str, list[str]]:
        validated: list[tuple[int, int, str, str]] = []
        occupied: list[tuple[int, int]] = []

        for index, patch in enumerate(patches):
            if not isinstance(patch, dict):
                raise LLMResponseValidationError(
                    f"patches[{index}] 必须是 object。"
                )
            if set(patch) != {"old_sql", "new_sql", "reason"}:
                raise LLMResponseValidationError(
                    f"patches[{index}] 必须且只能包含 old_sql、new_sql、reason。"
                )

            old_sql = patch["old_sql"]
            new_sql = patch["new_sql"]
            reason = patch["reason"]

            if not isinstance(old_sql, str) or not old_sql:
                raise LLMResponseValidationError(
                    f"patches[{index}].old_sql 必须是非空字符串。"
                )
            if not isinstance(new_sql, str):
                raise LLMResponseValidationError(
                    f"patches[{index}].new_sql 必须是字符串。"
                )
            if not isinstance(reason, str) or not reason.strip():
                raise LLMResponseValidationError(
                    f"patches[{index}].reason 必须是非空字符串。"
                )

            if sql.count(old_sql) != 1:
                raise LLMResponseValidationError(
                    f"patches[{index}].old_sql 必须在原 SQL 中唯一出现。"
                )

            start = sql.index(old_sql)
            end = start + len(old_sql)
            if any(
                not (end <= other_start or start >= other_end)
                for other_start, other_end in occupied
            ):
                raise LLMResponseValidationError(
                    "optimization patches 之间不得重叠。"
                )

            occupied.append((start, end))
            validated.append((start, end, new_sql, reason.strip()))

        candidate = sql
        reasons: list[str] = []
        for start, end, new_sql, reason in sorted(
            validated,
            key=lambda item: item[0],
            reverse=True,
        ):
            candidate = candidate[:start] + new_sql + candidate[end:]
            reasons.append(reason)
        reasons.reverse()

        return candidate, reasons

    def _parse_result(
        self,
        *,
        sql: str,
        raw_result: dict[str, Any],
    ) -> OptimizationResult:
        if not isinstance(raw_result, dict):
            raise LLMResponseValidationError(
                "LLM Optimize 返回结果必须是 JSON object。"
            )

        required_fields = {
            "summary",
            "suggestions",
            "candidate_sql",
            "rewrite_reason",
            "assumptions",
            "confidence",
        }

        missing_fields = required_fields - set(raw_result.keys())
        if missing_fields:
            raise LLMResponseValidationError(
                "LLM Optimize 返回结果缺少字段："
                f"{sorted(missing_fields)}"
            )

        suggestions_value = raw_result["suggestions"]
        if not isinstance(suggestions_value, list):
            raise LLMResponseValidationError(
                "suggestions 必须是数组。"
            )

        suggestions = tuple(
            self._parse_suggestion(item)
            for item in suggestions_value
        )

        candidate_sql = raw_result["candidate_sql"]
        if candidate_sql is not None:
            if not isinstance(candidate_sql, str):
                raise LLMResponseValidationError(
                    "candidate_sql 必须是字符串或 null。"
                )
            candidate_sql = candidate_sql.strip() or None

        assumptions = raw_result["assumptions"]
        if not isinstance(assumptions, list):
            raise LLMResponseValidationError(
                "assumptions 必须是数组。"
            )

        confidence = self._parse_confidence(
            raw_result["confidence"]
        )

        rewrite_reason = raw_result["rewrite_reason"]
        if rewrite_reason is not None and not isinstance(
            rewrite_reason,
            str,
        ):
            raise LLMResponseValidationError(
                "rewrite_reason 必须是字符串或 null。"
            )

        return OptimizationResult(
            original_sql=sql,
            summary=str(raw_result["summary"]),
            suggestions=suggestions,
            candidate_sql=candidate_sql,
            rewrite_reason=rewrite_reason,
            assumptions=tuple(
                str(item) for item in assumptions
            ),
            confidence=confidence,
            raw_output=raw_result,
        )

    @staticmethod
    def _parse_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError) as error:
            raise LLMResponseValidationError(
                "confidence 必须是数字。"
            ) from error

        if not 0 <= confidence <= 1:
            raise LLMResponseValidationError(
                "confidence 必须在 0 到 1 之间。"
            )
        return confidence

    @staticmethod
    def _parse_suggestion(
        item: Any,
    ) -> OptimizationSuggestion:
        if not isinstance(item, dict):
            raise LLMResponseValidationError(
                "Optimization suggestion 必须是 object。"
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
        missing = required - set(item.keys())
        if missing:
            raise LLMResponseValidationError(
                "Optimization suggestion 缺少字段："
                f"{sorted(missing)}"
            )

        priority = str(item["priority"]).lower()
        if priority not in {"low", "medium", "high"}:
            raise LLMResponseValidationError(
                "priority 必须是 low、medium 或 high。"
            )

        return OptimizationSuggestion(
            category=str(item["category"]),
            priority=priority,
            description=str(item["description"]),
            reason=str(item["reason"]),
            expected_benefit=str(item["expected_benefit"]),
            risk=str(item["risk"]),
            requires_execution_validation=bool(
                item["requires_execution_validation"]
            ),
        )
