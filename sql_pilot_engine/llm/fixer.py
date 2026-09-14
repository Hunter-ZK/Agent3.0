from __future__ import annotations

from typing import Any

from sql_pilot_engine.context.builder import QueryContext
from sql_pilot_engine.core.models import FixedSqlResult
from sql_pilot_engine.llm.errors import LLMResponseValidationError
from sql_pilot_engine.llm.fix_diagnoser import render_fix_diagnoses
from sql_pilot_engine.llm.fix_prompts import (
    FIX_JSON_SCHEMA,
    FIX_REPAIR_SYSTEM_PROMPT,
    FIX_SYSTEM_PROMPT,
    PATCH_FIX_JSON_SCHEMA,
    PATCH_FIX_SYSTEM_PROMPT,
    build_fix_repair_prompt,
    build_fix_user_prompt,
    build_patch_fix_user_prompt,
)
from sql_pilot_engine.llm.protocols import StructuredGenerationModel


MAX_FULL_REWRITE_CHARS = 16000


class LLMFixer:
    """
    Production LLM Fixer。

    `diagnoses=None` 表示兼容性的直接调用，允许按既有 Review Context 生成 Candidate；
    正式 FixService 会显式传入 diagnoses（包括空数组），此时强制执行 Diagnosis Gate：
    只有 confirmed + auto_fix_safe + required_context 为空的诊断才允许模型继续修改。
    """

    def __init__(
        self,
        client: StructuredGenerationModel,
        *,
        max_full_rewrite_chars: int = MAX_FULL_REWRITE_CHARS,
    ) -> None:
        self.client = client
        self.max_full_rewrite_chars = max_full_rewrite_chars

    def fix(
        self,
        original_sql: str,
        deterministic_pre_fix_sql: str,
        review_issues_text: str,
        analysis_context_text: str,
        metadata_context_text: str,
        program_evidence_context_text: str = "",
        query_context: QueryContext | None = None,
        diagnoses: list[dict[str, Any]] | None = None,
    ) -> FixedSqlResult:
        diagnosis_enforced = diagnoses is not None
        diagnoses_list = list(diagnoses or [])

        if diagnosis_enforced:
            safe_diagnoses = [
                item
                for item in diagnoses_list
                if item.get("diagnosis_status") == "confirmed"
                and item.get("auto_fix_safe") is True
                and not item.get("required_context")
            ]
            if not safe_diagnoses:
                return FixedSqlResult(
                    fixed_sql=original_sql,
                    applied_fixes=[],
                    manual_notes=[
                        "No confirmed auto-fix-safe diagnosis is available. "
                        "Production Fix is held for human review instead of guessing."
                    ],
                    source="llm_diagnosis_hold",
                    diagnoses=diagnoses_list,
                    validation={
                        "diagnosis_gate": "hold",
                        "safe_diagnosis_count": 0,
                    },
                )
        else:
            safe_diagnoses = diagnoses_list

        diagnosis_text = render_fix_diagnoses(
            safe_diagnoses if diagnosis_enforced else diagnoses_list
        )

        if len(original_sql) > self.max_full_rewrite_chars:
            result = self._fix_with_scoped_patches(
                original_sql=original_sql,
                deterministic_pre_fix_sql=deterministic_pre_fix_sql,
                review_issues_text=review_issues_text,
                diagnosis_text=diagnosis_text,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                program_evidence_context_text=program_evidence_context_text,
                query_context=query_context,
            )
            result.diagnoses = diagnoses_list
            result.validation = {
                **result.validation,
                "diagnosis_gate": "passed" if diagnosis_enforced else "legacy_direct",
                "safe_diagnosis_count": len(safe_diagnoses),
            }
            return result

        user_prompt = build_fix_user_prompt(
            original_sql=original_sql,
            deterministic_pre_fix_sql=deterministic_pre_fix_sql,
            review_issues_text=review_issues_text,
            diagnosis_text=diagnosis_text,
            analysis_context_text=analysis_context_text,
            metadata_context_text=metadata_context_text,
            program_evidence_context_text=program_evidence_context_text,
            query_context=query_context,
        )
        raw_result = self.client.generate_json(
            system_prompt=FIX_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=FIX_JSON_SCHEMA,
        )

        try:
            result = self._parse_result(raw_result)
        except LLMResponseValidationError as first_error:
            repaired_result = self.client.generate_json(
                system_prompt=FIX_REPAIR_SYSTEM_PROMPT,
                user_prompt=build_fix_repair_prompt(
                    raw_result=raw_result,
                    error_message=str(first_error),
                ),
                json_schema=FIX_JSON_SCHEMA,
            )
            result = self._parse_result(repaired_result)

        result.diagnoses = diagnoses_list
        result.validation = {
            **result.validation,
            "diagnosis_gate": "passed" if diagnosis_enforced else "legacy_direct",
            "safe_diagnosis_count": len(safe_diagnoses),
        }
        return result

    def _fix_with_scoped_patches(
        self,
        *,
        original_sql: str,
        deterministic_pre_fix_sql: str,
        review_issues_text: str,
        diagnosis_text: str,
        analysis_context_text: str,
        metadata_context_text: str,
        program_evidence_context_text: str,
        query_context: QueryContext | None,
    ) -> FixedSqlResult:
        raw_result = self.client.generate_json(
            system_prompt=PATCH_FIX_SYSTEM_PROMPT,
            user_prompt=build_patch_fix_user_prompt(
                original_sql=original_sql,
                deterministic_pre_fix_sql=deterministic_pre_fix_sql,
                review_issues_text=review_issues_text,
                diagnosis_text=diagnosis_text,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                program_evidence_context_text=program_evidence_context_text,
                query_context=query_context,
            ),
            json_schema=PATCH_FIX_JSON_SCHEMA,
        )

        if not isinstance(raw_result, dict):
            raise LLMResponseValidationError(
                "LLM Patch Fix 返回结果必须是 JSON object。"
            )
        if set(raw_result) != {"patches", "manual_notes"}:
            raise LLMResponseValidationError(
                "LLM Patch Fix 根对象必须且只能包含 patches、manual_notes。"
            )

        patches = raw_result["patches"]
        manual_notes = raw_result["manual_notes"]
        if not isinstance(patches, list):
            raise LLMResponseValidationError("patches 必须是数组。")
        if not isinstance(manual_notes, list):
            raise LLMResponseValidationError("manual_notes 必须是数组。")

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
            if original_sql.count(old_sql) != 1:
                raise LLMResponseValidationError(
                    f"patches[{index}].old_sql 必须在原 SQL 中唯一出现。"
                )

            start = original_sql.index(old_sql)
            end = start + len(old_sql)
            if any(
                not (end <= other_start or start >= other_end)
                for other_start, other_end in occupied
            ):
                raise LLMResponseValidationError("scoped patches 之间不得重叠。")
            occupied.append((start, end))
            validated.append((start, end, new_sql, reason.strip()))

        candidate = original_sql
        applied_fixes: list[str] = []
        for start, end, new_sql, reason in sorted(
            validated,
            key=lambda item: item[0],
            reverse=True,
        ):
            candidate = candidate[:start] + new_sql + candidate[end:]
            applied_fixes.append(reason)
        applied_fixes.reverse()

        return FixedSqlResult(
            fixed_sql=candidate,
            applied_fixes=applied_fixes,
            manual_notes=[str(item) for item in manual_notes],
            source="llm_patch",
        )

    def _parse_result(self, raw_result: dict[str, Any]) -> FixedSqlResult:
        if not isinstance(raw_result, dict):
            raise LLMResponseValidationError(
                "LLM Fix 返回结果必须是 JSON object。"
            )
        required_fields = {"fixed_sql", "applied_fixes", "manual_notes"}
        missing_fields = required_fields - set(raw_result.keys())
        if missing_fields:
            raise LLMResponseValidationError(
                f"LLM Fix 返回结果缺少字段：{sorted(missing_fields)}"
            )
        extra_fields = set(raw_result.keys()) - required_fields
        if extra_fields:
            raise LLMResponseValidationError(
                f"LLM Fix 返回结果包含多余字段：{sorted(extra_fields)}"
            )

        fixed_sql = raw_result["fixed_sql"]
        applied_fixes = raw_result["applied_fixes"]
        manual_notes = raw_result["manual_notes"]
        if not isinstance(fixed_sql, str):
            raise LLMResponseValidationError("fixed_sql 必须是字符串。")
        if not isinstance(applied_fixes, list):
            raise LLMResponseValidationError("applied_fixes 必须是数组。")
        if not isinstance(manual_notes, list):
            raise LLMResponseValidationError("manual_notes 必须是数组。")

        return FixedSqlResult(
            fixed_sql=fixed_sql,
            applied_fixes=[str(item) for item in applied_fixes],
            manual_notes=[str(item) for item in manual_notes],
            source="llm",
        )
