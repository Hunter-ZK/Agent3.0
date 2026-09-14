"""
SQL Review / Trusted SQL Core 的内部结果模型。

【架构位置】
Rule / Metadata Validator / LLM Reviewer
    -> Issue
    -> ReviewResult
    -> Review Routing / TrustedSQLWorkflow
    -> API Response Projection

FixService / LLM Fixer
    -> FixSuggestion / FixedSqlResult

【核心设计】
1. Issue.action 是“是否阻断、是否修复、是否澄清”的唯一路由事实源；
2. severity 只表示风险等级，不能替代 action；
3. blocking 不单独存储，而是从 action 派生，避免同一 Issue 出现 action=ADVISORY 但 blocking=True 的矛盾；
4. Domain Model 与外部 Response 分离，通过 to_dict() 做稳定序列化投影。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from sql_pilot_engine.core.enums import (
    FixType,
    IssueAction,
    IssueSource,
    Severity,
)

if TYPE_CHECKING:
    from sql_pilot_engine.analysis.sql_analysis import SQLAnalysisResult


@dataclass
class Issue:
    """SQL Review 发现的一条结构化问题。"""

    rule_id: str
    title: str
    severity: Severity
    message: str
    suggestion: str
    evidence: str
    category: str

    source: IssueSource = IssueSource.RULE
    confidence: float = 1.0
    location: str | None = None
    action: IssueAction = IssueAction.HUMAN_REVIEW
    missing_context: tuple[str, ...] = ()
    auto_fixable: bool = False
    requires_metadata: bool = False
    requires_knowledge: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.action in {
            IssueAction.AUTO_FIX,
            IssueAction.CONTEXT_REQUIRED,
            IssueAction.HUMAN_REVIEW,
            IssueAction.BLOCK,
        }

    def to_dict(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["source"] = self.source.value
        data["action"] = self.action.value
        data["blocking"] = self.blocking
        return data


@dataclass
class FixSuggestion:
    """针对单个 Issue 的局部修复建议。"""

    issue_rule_id: str
    title: str
    fix_type: FixType
    explanation: str
    suggested_sql: str | None = None
    confidence: float = 0.8

    def to_dict(self) -> dict:
        data = asdict(self)
        data["fix_type"] = self.fix_type.value
        return data


@dataclass
class FixedSqlResult:
    """
    Fix Stage 产出的候选 SQL、诊断和本阶段验证信息。

    diagnoses 是“为什么要修”的结构化事实/模型判断；validation 只记录 Fix Stage 已完成的
    结构性 Gate。它们都不能把 Candidate 自动升级为 Trusted SQL；完整可信结论仍需 Re-review、
    Critic、必要时 Simulator / HITL。
    """

    fixed_sql: str
    applied_fixes: list[str] = field(default_factory=list)
    manual_notes: list[str] = field(default_factory=list)
    source: str = "auto"
    diagnoses: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewResult:
    """SQL Review Stage 的内部结构化汇总结果。"""

    file_path: str
    risk_level: Severity
    issue_count: int
    issues: list[Issue]
    reviewed_sql: str = ""
    fix_suggestions: list[FixSuggestion] = field(default_factory=list)
    fixed_sql_result: FixedSqlResult | None = None
    analysis_result: SQLAnalysisResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "reviewed_sql": self.reviewed_sql,
            "risk_level": self.risk_level.value,
            "issue_count": self.issue_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "fix_suggestions": [item.to_dict() for item in self.fix_suggestions],
            "fixed_sql_result": (
                self.fixed_sql_result.to_dict()
                if self.fixed_sql_result is not None
                else None
            ),
        }
