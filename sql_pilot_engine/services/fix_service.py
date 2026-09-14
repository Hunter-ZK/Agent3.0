from __future__ import annotations

from dataclasses import replace

from sql_pilot_engine.analysis.sql_analysis import SQLAnalysisAdapter
from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.core.models import FixedSqlResult, ReviewResult
from sql_pilot_engine.evidence.program_context import (
    ProgramEvidenceContext,
    ProgramEvidenceContextBuilder,
    ProgramEvidenceContextError,
)
from sql_pilot_engine.fixing.auto_fixer import generate_fixed_sql
from sql_pilot_engine.llm.context_builder import (
    build_analysis_context_text,
    build_metadata_context_text,
)
from sql_pilot_engine.llm.fix_diagnoser import LLMFixDiagnoser
from sql_pilot_engine.llm.fixer import LLMFixer
from sql_pilot_engine.llm.protocols import StructuredGenerationModel
from sql_pilot_engine.llm.review_prompts import build_issues_text
from sql_pilot_engine.services.review_service import ReviewService


class FixService:
    """
    Production SQL Fix。

    Review -> Diagnosis -> Candidate/Patch -> Program Structural Gate。
    完整可信闭环仍由上层 Re-review -> Critic -> HITL 完成。
    """

    def __init__(
        self,
        review_service: ReviewService,
        llm_client: StructuredGenerationModel | None = None,
        analysis_adapter: SQLAnalysisAdapter | None = None,
        program_context_builder: ProgramEvidenceContextBuilder | None = None,
    ) -> None:
        self.review_service = review_service
        self.llm_client = llm_client
        self.analysis_adapter = analysis_adapter or SQLAnalysisAdapter()
        self.program_context_builder = (
            program_context_builder or ProgramEvidenceContextBuilder()
        )

    def fix(
        self,
        context: SQLExecutionContext,
        *,
        review_result: ReviewResult | None = None,
    ) -> ReviewResult:
        if not context.fix_sql:
            raise ValueError("FixService requires fix_sql=True.")

        if review_result is None:
            review_result = self.review_service.review(
                replace(context, fix_sql=False)
            )
        elif review_result.reviewed_sql != context.sql:
            raise ValueError(
                "The supplied review_result does not belong to the SQL being fixed."
            )

        analysis = review_result.analysis_result
        if analysis is None:
            analysis = self.analysis_adapter.analyze(
                sql=context.sql,
                dialect=context.dialect,
            )

        if analysis.parse_result.success and analysis.facts is not None:
            analysis_context_text = build_analysis_context_text(
                facts=analysis.facts,
                dialect=context.dialect,
            )
            metadata_context_text = build_metadata_context_text(
                facts=analysis.facts,
                metadata_provider=context.metadata_provider,
            )
        else:
            analysis_context_text = "SQL 结构分析不可用。"
            metadata_context_text = "SQL 结构分析失败，因此未构建元数据上下文。"

        original_program_context, program_evidence_context_text = (
            self._build_program_context(context)
        )

        fixed_sql_result = self._generate_fixed_sql(
            context=context,
            review_result=review_result,
            analysis_context_text=analysis_context_text,
            metadata_context_text=metadata_context_text,
            program_evidence_context_text=program_evidence_context_text,
        )
        fixed_sql_result = self._validate_candidate_structure(
            context=context,
            original_program_context=original_program_context,
            candidate=fixed_sql_result,
        )

        return ReviewResult(
            file_path=review_result.file_path,
            reviewed_sql=context.sql,
            risk_level=review_result.risk_level,
            issue_count=review_result.issue_count,
            issues=review_result.issues,
            fix_suggestions=review_result.fix_suggestions,
            fixed_sql_result=fixed_sql_result,
            analysis_result=analysis,
        )

    def _build_program_context(
        self,
        context: SQLExecutionContext,
    ) -> tuple[ProgramEvidenceContext | None, str]:
        try:
            program_context = self.program_context_builder.build(
                context.sql,
                dialect=context.dialect,
                metadata_provider=context.metadata_provider,
            )
            return program_context, program_context.render_for_llm()
        except ProgramEvidenceContextError as exc:
            return None, f"Program/Evidence Context unavailable: {exc}"

    def _generate_fixed_sql(
        self,
        *,
        context: SQLExecutionContext,
        review_result: ReviewResult,
        analysis_context_text: str,
        metadata_context_text: str,
        program_evidence_context_text: str,
    ) -> FixedSqlResult:
        deterministic_result = generate_fixed_sql(
            sql=context.sql,
            issues=review_result.issues,
        )

        if context.fix_provider == "auto":
            deterministic_result.validation = {
                "diagnosis_stage": "not_required",
                "candidate_kind": "deterministic",
            }
            return deterministic_result

        if context.fix_provider != "llm":
            raise ValueError(
                f"Unsupported fix_provider: {context.fix_provider!r}"
            )
        if self.llm_client is None:
            raise RuntimeError(
                "fix_provider='llm' but no LLM client is configured."
            )

        review_issues_text = build_issues_text(review_result.issues)
        if context.critic_feedback:
            feedback_text = "\n".join(
                f"- {item}" for item in context.critic_feedback
            )
            review_issues_text += (
                "\n\n## Critic Feedback\n" + feedback_text
            )

        diagnosis_error: str | None = None
        try:
            diagnoses = LLMFixDiagnoser(self.llm_client).diagnose(
                issues=[item.to_dict() for item in review_result.issues],
                original_sql=context.sql,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                program_evidence_context_text=program_evidence_context_text,
            )
        except Exception as exc:
            diagnoses = []
            diagnosis_error = str(exc)

        result = LLMFixer(client=self.llm_client).fix(
            original_sql=context.sql,
            deterministic_pre_fix_sql=deterministic_result.fixed_sql,
            review_issues_text=review_issues_text,
            analysis_context_text=analysis_context_text,
            metadata_context_text=metadata_context_text,
            program_evidence_context_text=program_evidence_context_text,
            query_context=context.query_context,
            diagnoses=diagnoses,
        )
        result.validation = {
            **result.validation,
            "diagnosis_stage": "passed" if diagnosis_error is None else "degraded",
            "diagnosed_issue_count": len(diagnoses),
        }
        if diagnosis_error is not None:
            result.manual_notes.append(
                "Fix Diagnosis unavailable; candidate used Review/Evidence only: "
                + diagnosis_error
            )
        return result

    def _validate_candidate_structure(
        self,
        *,
        context: SQLExecutionContext,
        original_program_context: ProgramEvidenceContext | None,
        candidate: FixedSqlResult,
    ) -> FixedSqlResult:
        if original_program_context is None:
            candidate.validation = {
                **candidate.validation,
                "program_structure": "not_comparable",
            }
            return candidate
        if candidate.fixed_sql == context.sql:
            candidate.validation = {
                **candidate.validation,
                "program_structure": "no_change",
            }
            return candidate

        try:
            candidate_context = self.program_context_builder.build(
                candidate.fixed_sql,
                dialect=context.dialect,
            )
        except ProgramEvidenceContextError as exc:
            return self._reject_candidate(
                context=context,
                candidate=candidate,
                reason=f"Candidate SQL failed Program Analysis: {exc}",
            )

        original_program = original_program_context.program
        candidate_program = candidate_context.program
        if len(candidate_program.statements) != len(original_program.statements):
            return self._reject_candidate(
                context=context,
                candidate=candidate,
                reason=(
                    "Candidate changed the number of business statements "
                    f"from {len(original_program.statements)} "
                    f"to {len(candidate_program.statements)}."
                ),
            )

        original_targets = tuple(
            statement.write_target.table_name
            if statement.write_target is not None
            else None
            for statement in original_program.statements
        )
        candidate_targets = tuple(
            statement.write_target.table_name
            if statement.write_target is not None
            else None
            for statement in candidate_program.statements
        )
        if candidate_targets != original_targets:
            return self._reject_candidate(
                context=context,
                candidate=candidate,
                reason=(
                    "Candidate changed write-target identity; production Fix "
                    "does not auto-accept target-table changes."
                ),
            )

        candidate.validation = {
            **candidate.validation,
            "program_structure": "passed",
            "statement_count_preserved": True,
            "write_targets_preserved": True,
        }
        return candidate

    @staticmethod
    def _reject_candidate(
        *,
        context: SQLExecutionContext,
        candidate: FixedSqlResult,
        reason: str,
    ) -> FixedSqlResult:
        return FixedSqlResult(
            fixed_sql=context.sql,
            applied_fixes=[],
            manual_notes=(
                list(candidate.manual_notes)
                + ["LLM candidate rejected by production structural gate: " + reason]
            ),
            source="rejected_candidate",
            diagnoses=list(candidate.diagnoses),
            validation={
                **candidate.validation,
                "program_structure": "rejected",
                "reason": reason,
            },
        )
