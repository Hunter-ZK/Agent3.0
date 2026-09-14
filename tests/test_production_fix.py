from __future__ import annotations

import pytest

from sql_pilot_engine.core.enums import IssueAction, IssueSource, Severity
from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.core.models import FixedSqlResult, Issue, ReviewResult
from sql_pilot_engine.llm.errors import LLMResponseValidationError
from sql_pilot_engine.llm.fix_diagnoser import LLMFixDiagnoser
from sql_pilot_engine.llm.fixer import LLMFixer
from sql_pilot_engine.services.fix_service import FixService


def _required_fields(json_schema: dict) -> set[str]:
    schema = json_schema.get("schema", json_schema)
    return set(schema.get("required", []))


class _PatchModel:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system_prompt = ""
        self.calls = 0

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = user_prompt
        _ = json_schema
        self.calls += 1
        self.system_prompt = system_prompt
        return self.payload


class _DiagnosisThenFixModel:
    def __init__(
        self,
        *,
        diagnosis: dict,
        fixed_sql: str | None = None,
    ) -> None:
        self.diagnosis = diagnosis
        self.fixed_sql = fixed_sql
        self.calls: list[str] = []

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = system_prompt
        _ = user_prompt
        required = _required_fields(json_schema)
        self.calls.append(",".join(sorted(required)))

        if "diagnoses" in required:
            return {"diagnoses": [self.diagnosis]}

        if "fixed_sql" in required:
            assert self.fixed_sql is not None
            return {
                "fixed_sql": self.fixed_sql,
                "applied_fixes": ["按已确认诊断修复边界条件"],
                "manual_notes": [],
            }

        raise AssertionError(f"Unexpected schema: {required}")


def _issue() -> Issue:
    return Issue(
        rule_id="BOUNDARY_RULE",
        title="边界条件需要修正",
        severity=Severity.MEDIUM,
        message="amount > 0 与已确认边界不一致",
        suggestion="使用 amount >= 0",
        evidence="amount > 0",
        category="semantic",
        source=IssueSource.RULE,
        action=IssueAction.HUMAN_REVIEW,
        auto_fixable=False,
    )


def _review_result(sql: str) -> ReviewResult:
    return ReviewResult(
        file_path="<memory>",
        reviewed_sql=sql,
        risk_level=Severity.MEDIUM,
        issue_count=1,
        issues=[_issue()],
    )


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

    with pytest.raises(LLMResponseValidationError, match="唯一出现"):
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
    assert result.validation["program_structure"] == "rejected"
    assert any(
        "write-target identity" in note
        for note in result.manual_notes
    )


def test_fix_diagnoser_filters_hallucinated_rule_and_downgrades_unsafe_confidence():
    model = _PatchModel(
        {
            "diagnoses": [
                {
                    "rule_id": "BOUNDARY_RULE",
                    "diagnosis_status": "confirmed",
                    "location": "amount > 0",
                    "root_cause": "边界条件不符合已确认规则",
                    "impact": "遗漏 amount=0 记录",
                    "proposed_fix": "改为 amount >= 0",
                    "confidence": 0.55,
                    "auto_fix_safe": True,
                    "required_context": [],
                },
                {
                    "rule_id": "HALLUCINATED_RULE",
                    "diagnosis_status": "confirmed",
                    "root_cause": "不存在的问题",
                    "confidence": 1.0,
                    "auto_fix_safe": True,
                    "required_context": [],
                },
            ]
        }
    )

    result = LLMFixDiagnoser(model).diagnose(
        issues=[_issue().to_dict()],
        original_sql="SELECT amount FROM t WHERE amount > 0",
        analysis_context_text="analysis",
        metadata_context_text="metadata",
        program_evidence_context_text="program",
    )

    assert len(result) == 1
    assert result[0]["rule_id"] == "BOUNDARY_RULE"
    assert result[0]["auto_fix_safe"] is False


def test_formal_fix_service_applies_candidate_only_after_safe_diagnosis():
    sql = "SELECT amount FROM project_src.loan_detail WHERE amount > 0"
    candidate = "SELECT amount FROM project_src.loan_detail WHERE amount >= 0"
    model = _DiagnosisThenFixModel(
        diagnosis={
            "rule_id": "BOUNDARY_RULE",
            "diagnosis_status": "confirmed",
            "location": "amount > 0",
            "root_cause": "边界条件与已确认规则不一致",
            "impact": "遗漏 amount=0 记录",
            "proposed_fix": "使用 amount >= 0",
            "confidence": 0.95,
            "auto_fix_safe": True,
            "required_context": [],
        },
        fixed_sql=candidate,
    )
    service = FixService(
        review_service=object(),  # type: ignore[arg-type]
        llm_client=model,
    )

    result = service.fix(
        SQLExecutionContext(
            sql=sql,
            fix_sql=True,
            fix_provider="llm",
        ),
        review_result=_review_result(sql),
    )

    fixed = result.fixed_sql_result
    assert fixed is not None
    assert fixed.fixed_sql == candidate
    assert fixed.source == "llm"
    assert fixed.diagnoses[0]["auto_fix_safe"] is True
    assert fixed.validation["diagnosis_gate"] == "passed"
    assert fixed.validation["program_structure"] == "passed"
    assert len(model.calls) == 2


def test_formal_fix_service_holds_when_diagnosis_requires_context():
    sql = "SELECT amount FROM project_src.loan_detail WHERE amount > 0"
    model = _DiagnosisThenFixModel(
        diagnosis={
            "rule_id": "BOUNDARY_RULE",
            "diagnosis_status": "insufficient_context",
            "location": "amount > 0",
            "root_cause": "无法确认边界口径",
            "impact": "未知",
            "proposed_fix": None,
            "confidence": 0.9,
            "auto_fix_safe": True,
            "required_context": ["amount=0 是否属于正式统计口径"],
        },
    )
    service = FixService(
        review_service=object(),  # type: ignore[arg-type]
        llm_client=model,
    )

    result = service.fix(
        SQLExecutionContext(
            sql=sql,
            fix_sql=True,
            fix_provider="llm",
        ),
        review_result=_review_result(sql),
    )

    fixed = result.fixed_sql_result
    assert fixed is not None
    assert fixed.fixed_sql == sql
    assert fixed.source == "llm_diagnosis_hold"
    assert fixed.validation["diagnosis_gate"] == "hold"
    assert fixed.validation["program_structure"] == "no_change"
    assert len(model.calls) == 1
    assert "human review" in fixed.manual_notes[0].lower()
