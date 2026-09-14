from __future__ import annotations

import json
from dataclasses import replace

from sql_pilot_engine.analysis.sql_analysis import SQLAnalysisAdapter
from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.evidence.program_context import (
    ProgramEvidenceContext,
    ProgramEvidenceContextBuilder,
)
from sql_pilot_engine.llm.context_builder import (
    build_analysis_context_text,
    build_metadata_context_text,
)
from sql_pilot_engine.llm.optimization_advisor import LLMOptimizationAdvisor
from sql_pilot_engine.llm.optimizer import LLMOptimizer
from sql_pilot_engine.llm.protocols import StructuredGenerationModel
from sql_pilot_engine.optimization.models import (
    OptimizationResult,
    OptimizationSuggestion,
)
from sql_pilot_engine.schemas.responses import SQLExplainResponse
from sql_pilot_engine.services.review_service import ReviewService


class OptimizeService:
    """
    Production SQL Optimization。

    Flow:
        Evidence / Explain
            -> Opportunity Advisor
            -> rewrite-safe Gate
            -> Candidate / Scoped Patch
            -> Program Gate
            -> Trusted SQL Review Gate
            -> Candidate/HITL

    Statistics / Execution 依赖的机会只能成为建议，不能自动改写。
    """

    def __init__(
        self,
        llm_client: StructuredGenerationModel,
        analysis_adapter: SQLAnalysisAdapter | None = None,
        review_service: ReviewService | None = None,
        program_context_builder: ProgramEvidenceContextBuilder | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.analysis_adapter = analysis_adapter or SQLAnalysisAdapter()
        self.review_service = review_service
        self.program_context_builder = (
            program_context_builder or ProgramEvidenceContextBuilder()
        )

    def optimize(
        self,
        context: SQLExecutionContext,
        *,
        optimization_goals: list[str],
        explain_response: SQLExplainResponse | None = None,
    ) -> OptimizationResult:
        analysis = self.analysis_adapter.analyze(
            sql=context.sql,
            dialect=context.dialect,
        )
        if not analysis.parse_result.success:
            raise ValueError("Trusted SQL cannot be parsed during optimization.")
        facts = analysis.facts
        if facts is None:
            raise RuntimeError(
                "Successful optimization analysis must contain SQLFacts."
            )

        program_context = self.program_context_builder.build(
            context.sql,
            dialect=context.dialect,
            metadata_provider=context.metadata_provider,
        )
        analysis_context_text = build_analysis_context_text(
            facts=facts,
            dialect=context.dialect,
        )
        metadata_context_text = build_metadata_context_text(
            facts=facts,
            metadata_provider=context.metadata_provider,
        )
        explain_context_text = self._build_explain_context_text(explain_response)
        program_context_text = program_context.render_for_llm()

        advisor_summary, opportunities = LLMOptimizationAdvisor(
            self.llm_client
        ).analyze(
            dialect=context.dialect,
            optimization_goals=optimization_goals,
            analysis_context_text=analysis_context_text,
            metadata_context_text=metadata_context_text,
            explain_context_text=explain_context_text,
            program_evidence_context_text=program_context_text,
        )
        safe_opportunities = [
            item for item in opportunities if item["rewrite_safe"] is True
        ]

        if not safe_opportunities:
            suggestions = tuple(
                self._opportunity_to_suggestion(item)
                for item in opportunities
            )
            execution_required = any(
                item["requires_execution_validation"]
                or item["requires_statistics"]
                for item in opportunities
            )
            return OptimizationResult(
                original_sql=context.sql,
                summary=(
                    advisor_summary
                    or "Optimization analysis produced suggestions but no rewrite-safe candidate."
                ),
                suggestions=suggestions,
                candidate_sql=None,
                rewrite_reason=None,
                assumptions=(),
                confidence=max(
                    (item["confidence"] or 0.0 for item in opportunities),
                    default=0.0,
                ),
                opportunities=tuple(opportunities),
                validation={
                    "advisor_gate": "suggestions_only",
                    "rewrite_safe_opportunity_count": 0,
                    "program_structure": "not_run",
                    "trusted_sql_review": "not_run",
                    "execution_validation": (
                        "required" if execution_required else "not_required"
                    ),
                },
                raw_output={},
            )

        result = LLMOptimizer(client=self.llm_client).optimize(
            sql=context.sql,
            dialect=context.dialect,
            optimization_goals=optimization_goals,
            analysis_context_text=analysis_context_text,
            metadata_context_text=metadata_context_text,
            explain_context_text=explain_context_text,
            program_evidence_context_text=program_context_text,
            opportunities=safe_opportunities,
        )
        result = replace(
            result,
            opportunities=tuple(opportunities),
            validation={
                **result.validation,
                "advisor_gate": "passed",
                "total_opportunity_count": len(opportunities),
                "rewrite_safe_opportunity_count": len(safe_opportunities),
            },
        )

        if result.candidate_sql is None:
            return result
        return self._validate_candidate(
            context=context,
            original_program_context=program_context,
            result=result,
        )

    def _validate_candidate(
        self,
        *,
        context: SQLExecutionContext,
        original_program_context: ProgramEvidenceContext,
        result: OptimizationResult,
    ) -> OptimizationResult:
        assert result.candidate_sql is not None

        try:
            candidate_context = self.program_context_builder.build(
                result.candidate_sql,
                dialect=context.dialect,
            )
        except Exception as exc:
            return self._reject_candidate(
                result,
                reason=f"Optimization candidate failed Program Analysis: {exc}",
            )

        original_program = original_program_context.program
        candidate_program = candidate_context.program
        if len(candidate_program.statements) != len(original_program.statements):
            return self._reject_candidate(
                result,
                reason=(
                    "Optimization candidate changed business statement count "
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
                result,
                reason="Optimization candidate changed write-target identity.",
            )

        validation = {
            **result.validation,
            "program_structure": "passed",
            "statement_count_preserved": True,
            "write_targets_preserved": True,
        }

        if self.review_service is not None:
            candidate_review = self.review_service.review(
                replace(
                    context,
                    sql=result.candidate_sql,
                    fix_sql=False,
                )
            )
            blocking = [issue for issue in candidate_review.issues if issue.blocking]
            if blocking:
                return self._reject_candidate(
                    replace(result, validation=validation),
                    reason=(
                        "Optimization candidate failed Trusted SQL Review: "
                        + "; ".join(
                            f"{item.rule_id}: {item.message}"
                            for item in blocking[:5]
                        )
                    ),
                )
            validation["trusted_sql_review"] = "passed"
        else:
            validation["trusted_sql_review"] = "not_configured"

        validation["execution_validation"] = (
            "required"
            if any(
                item.requires_execution_validation
                for item in result.suggestions
            )
            else "not_required"
        )
        return replace(result, validation=validation)

    @staticmethod
    def _reject_candidate(
        result: OptimizationResult,
        *,
        reason: str,
    ) -> OptimizationResult:
        return OptimizationResult(
            original_sql=result.original_sql,
            summary=result.summary,
            suggestions=result.suggestions,
            candidate_sql=None,
            rewrite_reason=None,
            assumptions=(
                *result.assumptions,
                "Candidate rejected by production gate: " + reason,
            ),
            confidence=min(result.confidence, 0.5),
            opportunities=result.opportunities,
            validation={
                **result.validation,
                "candidate_gate": "rejected",
                "rejection_reason": reason,
            },
            raw_output=result.raw_output,
        )

    @staticmethod
    def _opportunity_to_suggestion(
        opportunity: dict,
    ) -> OptimizationSuggestion:
        evidence = opportunity.get("evidence")
        semantic_argument = opportunity.get("semantic_argument")
        reason_parts = [
            text
            for text in (evidence, semantic_argument)
            if text
        ]
        return OptimizationSuggestion(
            category=str(opportunity.get("category") or "general"),
            priority=str(opportunity.get("priority") or "medium"),
            description=str(opportunity.get("description") or ""),
            reason="; ".join(reason_parts),
            expected_benefit=str(opportunity.get("expected_benefit") or ""),
            risk=str(opportunity.get("risk") or ""),
            requires_execution_validation=bool(
                opportunity.get("requires_execution_validation")
                or opportunity.get("requires_statistics")
            ),
        )

    @staticmethod
    def _build_explain_context_text(
        explain_response: SQLExplainResponse | None,
    ) -> str:
        if explain_response is None or not explain_response.success:
            return "无可用 Explain Context。"

        payload = {
            "sql_summary": explain_response.sql_summary,
            "business_purpose": explain_response.business_purpose,
            "main_tables": explain_response.main_tables,
            "output_columns": explain_response.output_columns,
            "statement_explanations": explain_response.statement_explanations,
            "cte_steps": explain_response.cte_steps,
            "cte_dependencies": explain_response.cte_dependencies,
            "data_flow": explain_response.data_flow,
            "key_transformations": explain_response.key_transformations,
            "suspicious_points": explain_response.suspicious_points,
            "uncertainties": explain_response.uncertainties,
            "evidence": explain_response.evidence,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
