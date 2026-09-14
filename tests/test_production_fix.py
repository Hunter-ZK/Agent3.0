from __future__ import annotations

import pytest

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.core.models import FixedSqlResult
from sql_pilot_engine.llm.errors import LLMResponseValidationError
from sql_pilot_engine.llm.fixer import LLMFixer
from sql_pilot_engine.services.fix_service import FixService


class _PatchModel:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system_prompt = ""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = user_prompt
        _ = json_schema
        self.system_prompt = system_prompt
        return self.payload


def test_oversized_sql_uses_exact_scoped_patch_instead_of_full_rewrite():
    sql = "SELECT amount FROM project_src.loan_detail WHERE amount > 0"
    model = _PatchModel(
        {
            "patches": [
                {
                    "old_sql": "amount > 0",
                    "new_sql": "amount >= 0",
                    "reason": "修复边界条件",
                }
            ],
            "manual_notes": [],
        }
    )

    result = LLMFixer(
        client=model,
        max_full_rewrite_chars=10,
    ).fix(
        original_sql=sql,
        deterministic_pre_fix_sql=sql,
        review_issues_text="boundary issue",
        analysis_context_text="analysis",
        metadata_context_text="metadata",
        program_evidence_context_text="program evidence",
    )

    assert result.source == "llm_patch"
    assert result.fixed_sql.endswith("amount >= 0")
    assert result.applied_fixes == ["修复边界条件"]
    assert "scoped patch planner" in model.system_prompt


def test_scoped_patch_rejects_non_unique_source_fragment():
    sql = "SELECT id FROM a WHERE id > 0 UNION ALL SELECT id FROM b WHERE id > 0"
    model = _PatchModel(
        {
            "patches": [
                {
                    "old_sql": "id > 0",
                    "new_sql": "id >= 0",
                    "reason": "ambiguous patch",
                }
            ],
            "manual_notes": [],
        }
    )

    with pytest.raises(
        LLMResponseValidationError,
        match="唯一出现",
    ):
        LLMFixer(
            client=model,
            max_full_rewrite_chars=10,
        ).fix(
            original_sql=sql,
            deterministic_pre_fix_sql=sql,
            review_issues_text="issue",
            analysis_context_text="analysis",
            metadata_context_text="metadata",
            program_evidence_context_text="program evidence",
        )


def test_production_fix_rejects_candidate_that_changes_write_target():
    original = """
    INSERT OVERWRITE TABLE project_dwd.result_a
    SELECT id FROM project_src.source_a
    """
    candidate_sql = """
    INSERT OVERWRITE TABLE project_dwd.result_b
    SELECT id FROM project_src.source_a
    """

    service = FixService(review_service=object())  # type: ignore[arg-type]
    original_context = service.program_context_builder.build(original)

    result = service._validate_candidate_structure(
        context=SQLExecutionContext(sql=original),
        original_program_context=original_context,
        candidate=FixedSqlResult(
            fixed_sql=candidate_sql,
            applied_fixes=["change target"],
            source="llm_patch",
        ),
    )

    assert result.source == "rejected_candidate"
    assert result.fixed_sql == original
    assert any(
        "write-target identity" in note
        for note in result.manual_notes
    )
