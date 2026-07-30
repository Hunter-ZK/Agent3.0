# sql_review_agent/core/models.py

from dataclasses import asdict, dataclass, field

from sql_pilot_engine.core.enums import FixType, IssueSource, Severity, IssueAction


@dataclass
class Issue:
    """SQL Review 发现的问题。"""

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

    action: IssueAction = (
        IssueAction.HUMAN_REVIEW
    )

    auto_fixable: bool = False
    requires_metadata: bool = False
    requires_knowledge: bool = False
    blocking: bool = False

    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)

        data["severity"] = self.severity.value
        data["source"] = self.source.value
        data["action"] = self.action.value

        return data

@dataclass
class FixSuggestion:
    """零散修复建议；后续主要产物是 FixedSqlResult。"""

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
    """完整修复后 SQL。"""

    fixed_sql: str
    applied_fixes: list[str] = field(default_factory=list)
    manual_notes: list[str] = field(default_factory=list)
    source: str = "auto"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewResult:
    """SQL Review 最终结构化结果。"""

    file_path: str
    risk_level: Severity
    issue_count: int
    issues: list[Issue]
    fix_suggestions: list[FixSuggestion] = field(default_factory=list)
    fixed_sql_result: FixedSqlResult | None = None

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
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
