# sql_review_agent/schemas/responses.py

from dataclasses import dataclass, field
from typing import Any

from sql_pilot_engine.core.models import ReviewResult
from sql_pilot_engine.optimization.models import (
    OptimizationResult,
)


def default_explain_route_signals() -> dict[str, Any]:
    return {
        "need_metadata": False,
        "need_rag": False,
        "need_review": True,
        "need_human_confirm": False,
        "can_auto_fix": False,
        "next_node": "review_agent",
    }


def failed_explain_route_signals() -> dict[str, Any]:
    return {
        "need_metadata": False,
        "need_rag": False,
        "need_review": True,
        "need_human_confirm": False,
        "can_auto_fix": False,
        "next_node": "fallback_review",
    }


@dataclass
class SQLReviewResponse:
    """SQL Review Engine 的审查响应 DTO。

    raw_result 用于兼容当前 reporting/renderers.py 与旧测试；Web/API 层优先读取
    risk_level、issue_count、issues、summary 等稳定字段。
    """

    success: bool
    task_type: str
    file_path: str
    risk_level: str
    issue_count: int
    trace_id: str | None = None
    issues: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    raw_result: ReviewResult | None = None
    error_message: str | None = None

    @classmethod
    def from_review_result(cls, result: ReviewResult, trace_id: str | None = None,) -> "SQLReviewResponse":
        return cls(
            success=True,
            task_type="review",
            file_path=result.file_path,
            risk_level=result.risk_level.value,
            issue_count=result.issue_count,
            trace_id=trace_id,
            issues=[issue.to_dict() for issue in result.issues],
            summary={
                "risk_level": result.risk_level.value,
                "issue_count": result.issue_count,
                "has_fixed_sql": result.fixed_sql_result is not None,
            },
            raw_result=result,
        )

    @classmethod
    def failed(cls, task_type: str, file_path: str, error_message: str, trace_id: str | None = None) -> "SQLReviewResponse":
        return cls(
            success=False,
            task_type=task_type,
            file_path=file_path,
            risk_level="unknown",
            issue_count=0,
            trace_id=trace_id,
            issues=[],
            summary={},
            raw_result=None,
            error_message=error_message,
        )

    def to_dict(self, include_raw_result: bool = False) -> dict[str, Any]:
        data = {
            "success": self.success,
            "task_type": self.task_type,
            "file_path": self.file_path,
            "risk_level": self.risk_level,
            "issue_count": self.issue_count,
            "trace_id":self.trace_id,
            "issues": self.issues,
            "summary": self.summary,
            "error_message": self.error_message,
        }
        if include_raw_result:
            data["raw_result"] = self.raw_result.to_dict() if self.raw_result is not None else None
        return data


@dataclass
class SQLFixResponse(SQLReviewResponse):
    """SQL Review Engine 的修复响应 DTO。"""

    fixed_sql: str | None = None
    applied_fixes: list[str] = field(default_factory=list)
    manual_notes: list[str] = field(default_factory=list)
    fix_source: str | None = None

    @classmethod
    def from_review_result(cls, result: ReviewResult, trace_id: str|None = None,) -> "SQLFixResponse":
        fixed_sql_result = result.fixed_sql_result
        return cls(
            success=True,
            task_type="fix",
            file_path=result.file_path,
            risk_level=result.risk_level.value,
            issue_count=result.issue_count,
            trace_id=trace_id,
            issues=[issue.to_dict() for issue in result.issues],
            summary={
                "risk_level": result.risk_level.value,
                "issue_count": result.issue_count,
                "has_fixed_sql": fixed_sql_result is not None,
            },
            raw_result=result,
            fixed_sql=fixed_sql_result.fixed_sql if fixed_sql_result is not None else None,
            applied_fixes=fixed_sql_result.applied_fixes if fixed_sql_result is not None else [],
            manual_notes=fixed_sql_result.manual_notes if fixed_sql_result is not None else [],
            fix_source=fixed_sql_result.source if fixed_sql_result is not None else None,
        )

    @classmethod
    def failed(cls, task_type: str, file_path: str, error_message: str, trace_id: str|None = None) -> "SQLFixResponse":
        return cls(
            success=False,
            task_type=task_type,
            file_path=file_path,
            risk_level="unknown",
            issue_count=0,
            trace_id=trace_id,
            issues=[],
            summary={},
            raw_result=None,
            error_message=error_message,
        )

    def to_dict(self, include_raw_result: bool = False) -> dict[str, Any]:
        data = super().to_dict(include_raw_result=include_raw_result)
        data.update(
            {
                "fixed_sql": self.fixed_sql,
                "applied_fixes": self.applied_fixes,
                "manual_notes": self.manual_notes,
                "fix_source": self.fix_source,
            }
        )
        return data



@dataclass
class SQLExplainResponse:
    """SQL Explain Agent 的结构化输出。

    Explain 不是单纯生成自然语言说明，而是为后续 Review / Metadata / RAG /
    Critic / Human-in-the-loop 提供可消费的结构化状态。
    """

    success: bool
    task_type: str = "explain"
    file_path: str = "<memory>"
    trace_id: str | None = None
    error_message: str | None = None

    sql_summary: str = ""
    business_purpose: str | None = None

    main_tables: list[dict[str, Any]] = field(default_factory=list)
    output_columns: list[dict[str, Any]] = field(default_factory=list)

    cte_steps: list[dict[str, Any]] = field(default_factory=list)
    cte_dependencies: list[dict[str, Any]] = field(default_factory=list)

    suspicious_points: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)

    route_signals: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    raw_output: Any | None = None

    @classmethod
    def from_llm_payload(
        cls,
        payload: dict[str, Any],
        file_path: str = "<memory>",
        trace_id: str | None = None,
    ) -> "SQLExplainResponse":
        
        route_signals = payload.get("route_signals") or default_explain_route_signals()

        return cls(
            success=True,
            file_path=file_path,
            trace_id=trace_id,
            error_message=None,
            sql_summary=payload.get('sql_summary',""),
            business_purpose=payload.get('business_purpose'),
            main_tables=payload.get('main_tables',[]),
            output_columns=payload.get('output_columns',[]),
            cte_steps=payload.get('cte_steps',[]),
            cte_dependencies=payload.get('cte_dependencies',[]),
            suspicious_points=payload.get('suspicious_points',[]),
            uncertainties=payload.get('uncertainties',[]),
            route_signals=route_signals,
            evidence=payload.get('evidence',[]),
            raw_output=payload,
        )


    @classmethod
    def failed(
        cls,
        file_path: str,
        error_message: str,
        trace_id: str | None = None,
        raw_output: Any | None = None,
    ) -> "SQLExplainResponse":
        return cls(
            success=False,
            file_path=file_path,
            trace_id=trace_id,
            error_message=error_message,
            sql_summary="",
            business_purpose=None,
            output_columns=[],
            cte_steps=[],
            cte_dependencies=[],
            suspicious_points=[],
            uncertainties=[],
            route_signals=failed_explain_route_signals(),
            evidence=[],
            raw_output=raw_output,

        )


    def to_dict(self) -> dict[str, Any]:
        data = {
            "success": self.success,
            "task_type": self.task_type,
            "file_path": self.file_path,
            "trace_id": self.trace_id,
            "error_message": self.error_message,
            "sql_summary": self.sql_summary,
            "business_purpose": self.business_purpose,
            "main_tables": self.main_tables,
            "output_columns": self.output_columns,
            "cte_steps": self.cte_steps,
            "cte_dependencies": self.cte_dependencies,
            "suspicious_points": self.suspicious_points,
            "uncertainties": self.uncertainties,
            "route_signals": self.route_signals,
            "evidence": self.evidence,
            "raw_output": self.raw_output,
        }
        return data
    
@dataclass
class SQLOptimizeResponse:
    """
    Engine Optimize 的外部响应。

    candidate_sql 仍是候选，
    不是最终 Workflow SQL。
    """

    success: bool

    task_type: str = "optimize"

    file_path: str = "<memory>"

    trace_id: str | None = None

    status: str = "unknown"

    summary: str = ""

    suggestions: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    candidate_sql: str | None = None

    rewrite_reason: str | None = None

    assumptions: list[str] = field(
        default_factory=list
    )

    confidence: float = 0.0

    error_message: str | None = None

    raw_output: Any | None = None

    @classmethod
    def from_optimization_result(
        cls,
        *,
        result: OptimizationResult,
        file_path: str,
        trace_id: str | None,
    ) -> "SQLOptimizeResponse":

        if result.candidate_sql:
            status = (
                "candidate_generated"
            )

        elif result.suggestions:
            status = "suggestions"

        else:
            status = "no_optimization"

        return cls(
            success=True,
            file_path=file_path,
            trace_id=trace_id,
            status=status,
            summary=result.summary,
            suggestions=[
                {
                    "category": item.category,
                    "priority": item.priority,
                    "description": (
                        item.description
                    ),
                    "reason": item.reason,
                    "expected_benefit": (
                        item
                        .expected_benefit
                    ),
                    "risk": item.risk,
                    "requires_execution_validation": (
                        item
                        .requires_execution_validation
                    ),
                }
                for item
                in result.suggestions
            ],
            candidate_sql=(
                result.candidate_sql
            ),
            rewrite_reason=(
                result.rewrite_reason
            ),
            assumptions=list(
                result.assumptions
            ),
            confidence=result.confidence,
            raw_output=result.raw_output,
        )

    @classmethod
    def failed(
        cls,
        *,
        file_path: str,
        error_message: str,
        trace_id: str | None = None,
    ) -> "SQLOptimizeResponse":

        return cls(
            success=False,
            file_path=file_path,
            trace_id=trace_id,
            status="optimize_failed",
            error_message=(
                error_message
            ),
        )

@dataclass
class SQLCriticResponse:

    success: bool
    passed: bool
    trace_id: str | None = None
    status: str = "unknown"
    reason: str = ""
    need_human_confirm: bool = False
    need_retry: bool = False
    checked_items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None

    retry_instructions: list[str] = field(default_factory=list)
    raw_output: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "passed": self.passed,
            "trace_id": self.trace_id,
            "status": self.status,
            "reason": self.reason,
            "need_human_confirm": self.need_human_confirm,
            "need_retry": self.need_retry,
            "checked_items": self.checked_items,
            "warnings": self.warnings,
            "error_message": self.error_message,
            "retry_instructions": self.retry_instructions,
            "raw_output": self.raw_output,
        }
    

    @classmethod
    def from_llm_payload(
        cls,
        payload: dict[str, Any],
        trace_id: str | None = None,
        raw_output: Any | None = None,
    ) -> "SQLCriticResponse":
        
        passed = bool(payload.get("passed", False))
        need_retry = bool(payload.get("need_retry", False))
        need_human_confirm = bool(
            payload.get("need_human_confirm", False)
        )

        return cls(
            success=True,
            passed=passed,
            trace_id=trace_id,
            status=payload.get(
                "status",
                "passed" if passed else "failed",
            ),
            reason=payload.get("reason",""),
            need_retry=need_retry,
            need_human_confirm=need_human_confirm,
            checked_items=payload.get("checked_items", []),
            warnings=payload.get("warnings", []),
            retry_instructions=payload.get("retry_instructions", []),
            raw_output=raw_output,
        )


