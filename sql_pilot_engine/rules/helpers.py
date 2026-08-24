from sql_pilot_engine.core.enums import (
    IssueAction,
    IssueSource,
    Severity,
)
from sql_pilot_engine.core.models import (
    Issue,
)


def make_issue(
    *,
    rule_id: str,
    title: str,
    severity: Severity,
    message: str,
    suggestion: str,
    evidence: str,
    category: str,
    action: IssueAction = (
        IssueAction.HUMAN_REVIEW
    ),
    auto_fixable: bool = False,
    requires_metadata: bool = False,
    requires_knowledge: bool = False,
) -> Issue:

    return Issue(
        rule_id=rule_id,
        title=title,
        severity=severity,
        message=message,
        suggestion=suggestion,
        evidence=evidence,
        category=category,
        source=IssueSource.RULE,
        confidence=1.0,
        action=action,
        auto_fixable=auto_fixable,
        requires_metadata=(
            requires_metadata
        ),
        requires_knowledge=(
            requires_knowledge
        ),
    )