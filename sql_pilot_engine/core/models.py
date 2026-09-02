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
from typing import TYPE_CHECKING

from sql_pilot_engine.core.enums import (
    FixType,
    IssueAction,
    IssueSource,
    Severity,
)

if TYPE_CHECKING:
    # Analysis Result 只用于内部追踪，不进入普通 repr/compare，避免结果对象过重。
    from sql_pilot_engine.analysis.sql_analysis import SQLAnalysisResult


@dataclass
class Issue:
    """
    SQL Review 发现的一条结构化问题。

    【字段分组】
    - rule_id/title/category：稳定识别与分类；
    - severity/message/suggestion/evidence：给人和 Evaluation 阅读的风险说明；
    - source/confidence：说明判断来自哪里、置信程度如何；
    - action：Workflow 路由唯一事实源；
    - missing_context：只有 CONTEXT_REQUIRED 时才表示需要用户/业务补充的信息。

    LLM 产生 Issue 时，即使 severity=HIGH，也不能仅凭模型意见把 action 升级成 BLOCK；
    BLOCK 必须建立在确定性证据上。
    """

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

    # 默认 HUMAN_REVIEW 比默认 BLOCK 更安全：证据不足时交给人工，而不是伪造确定性结论。
    action: IssueAction = IssueAction.HUMAN_REVIEW

    # 仅 CONTEXT_REQUIRED 使用。它不是 Metadata 缺失清单，也不是 Reviewer 的推理过程。
    missing_context: tuple[str, ...] = ()

    # auto_fixable 与 action=AUTO_FIX 相关但不是同一个概念：前者描述能力，后者描述本次路由。
    auto_fixable: bool = False
    requires_metadata: bool = False
    requires_knowledge: bool = False

    # 扩展证据/规则附加数据。稳定字段应优先进入显式 Contract，而不是长期堆在 metadata。
    metadata: dict = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        """
        当前 Issue 是否阻止 SQL 直接成为 Trusted SQL。

        AUTO_FIX 也属于 blocking：虽然系统可能自动修，但修复完成并重新 Review 前原 SQL 仍不能通过。
        ADVISORY / IGNORE 不阻断。
        """

        return self.action in {
            IssueAction.AUTO_FIX,
            IssueAction.CONTEXT_REQUIRED,
            IssueAction.HUMAN_REVIEW,
            IssueAction.BLOCK,
        }

    def to_dict(self) -> dict:
        """
        将内部 dataclass 投影为 JSON 友好的字典。

        Enum 显式转换为 value，避免 API 层依赖 Python Enum 序列化细节；blocking 虽不存储，
        仍作为兼容字段输出给既有 Response/API。
        """

        data = asdict(self)
        data["severity"] = self.severity.value
        data["source"] = self.source.value
        data["action"] = self.action.value
        data["blocking"] = self.blocking
        return data


@dataclass
class FixSuggestion:
    """
    针对单个 Issue 的局部修复建议。

    它不是最终修复 SQL；主要可执行产物仍然是 FixedSqlResult。把二者分开可以同时保留
    “每个问题为什么建议这样修”和“最终合并后的完整 SQL”。
    """

    issue_rule_id: str
    title: str
    fix_type: FixType
    explanation: str
    suggested_sql: str | None = None
    confidence: float = 0.8

    def to_dict(self) -> dict:
        """输出 JSON 友好结构，并把 FixType Enum 显式转换成字符串。"""

        data = asdict(self)
        data["fix_type"] = self.fix_type.value
        return data


@dataclass
class FixedSqlResult:
    """
    Fix Stage 产出的完整候选 SQL 及修复说明。

    注意：fixed_sql 仍然只是“修复后的 Candidate”，必须重新进入 Review/Trust，不能因为经过 Fixer
    就自动升级为 Trusted SQL。
    """

    fixed_sql: str
    applied_fixes: list[str] = field(default_factory=list)
    manual_notes: list[str] = field(default_factory=list)
    source: str = "auto"

    def to_dict(self) -> dict:
        """该 DTO 不含 Enum，直接使用 asdict() 即可稳定序列化。"""

        return asdict(self)


@dataclass
class ReviewResult:
    """
    SQL Review Stage 的内部结构化汇总结果。

    issues 保存完整问题；issue_count/risk_level 是便于路由和展示的汇总字段；
    fixed_sql_result 仅在修复流程实际发生时存在；analysis_result 保留同一次 SQL Analysis 的
    内部引用，避免后续组件再次解析 SQL。
    """

    file_path: str
    risk_level: Severity
    issue_count: int
    issues: list[Issue]

    # reviewed_sql 保存本轮真正被审查的 SQL，便于审计和后续重审比较。
    reviewed_sql: str = ""

    fix_suggestions: list[FixSuggestion] = field(default_factory=list)
    fixed_sql_result: FixedSqlResult | None = None

    # Analysis AST/Facts 属于内部重对象，不参与 repr/compare，也不直接出现在 API Response。
    analysis_result: SQLAnalysisResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def to_dict(self) -> dict:
        """
        投影为稳定字典结构。

        所有嵌套 Domain DTO 都通过自己的 to_dict() 序列化，避免把内部 Enum/AnalysisResult
        意外泄漏到外部边界。
        """

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
