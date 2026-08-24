from dataclasses import dataclass
from enum import Enum
from typing import Any

from sql_pilot_engine.core.enums import IssueAction

from sql_pilot_engine.schemas.responses import SQLReviewResponse



class ReviewRoute(str, Enum):
    """Review完成后允许进入的流程分支。"""

    COMPLETE = "complete"
    BLOCK = "block"
    METADATA_REQUIRED = "metadata_required"
    KNOWLEDGE_REQUIRED = "knowledge_required"
    CONTEXT_REQUIRED = "context_required"
    HUMAN_REVIEW = "human_review"
    AUTO_FIX = "auto_fix"


@dataclass(frozen=True)
class ReviewRouteDecision:
    """Workflow对Review结果作出的确定性路由决策。"""

    route: ReviewRoute
    reason: str
    actionable_issue_count: int
    
    final_status: str | None = None
    
    

def _read_action(
    issue: dict[str, Any],
) -> str:
    
    action = issue.get("action")
    
    if isinstance(action, IssueAction):
        return action.value
    
    if isinstance(action, str):
        return action
    
    return IssueAction.HUMAN_REVIEW.value


def decide_review_route(
    response: SQLReviewResponse,
) -> ReviewRouteDecision:
    
    if not response.success:
        raise ValueError(
            "Cannot route a failed review response."
        )

    NON_BLOCKING_ACTIONS = {
        IssueAction.ADVISORY.value,
        IssueAction.IGNORE.value,
    }

    actionable_issues = [
        issue
        for issue in response.issues
        if _read_action(issue)
        not in NON_BLOCKING_ACTIONS
    ]
    
    if not actionable_issues:
        if response.issue_count == 0:
            final_status = "no_issue"
            reason = "No issues were found."
        else:
            final_status = "trusted_with_advisories"
            reason = (
                "Only non-blocking advisory issues remain."
            )

        return ReviewRouteDecision(
            route=ReviewRoute.COMPLETE,
            reason=reason,
            actionable_issue_count=0,
            final_status=final_status,
        )

    if any(
        bool(issue.get("blocking"))
        or _read_action(issue)
        == IssueAction.BLOCK.value
        for issue in actionable_issues
    ):
        return ReviewRouteDecision(
            route=ReviewRoute.BLOCK,
            reason="A blocking issue exists.",
            actionable_issue_count=len(
                actionable_issues
            ),
            final_status="blocked",
        )
        
    needs_metadata = any(
        bool(issue.get("requires_metadata"))
        for issue in actionable_issues
    )

    needs_knowledge = any(
        bool(issue.get("requires_knowledge"))
        for issue in actionable_issues
    )

    has_context_action = any(
        _read_action(issue)
        == IssueAction.CONTEXT_REQUIRED.value
        for issue in actionable_issues
    )

    if needs_metadata and needs_knowledge:
        return ReviewRouteDecision(
            route=ReviewRoute.CONTEXT_REQUIRED,
            reason=(
                "Metadata and knowledge "
                "context are both required."
            ),
            actionable_issue_count=len(
                actionable_issues
            ),
            final_status = "metadata&knowledge_required",
        )
        
    if needs_metadata:
        return ReviewRouteDecision(
            route=ReviewRoute.METADATA_REQUIRED,
            reason="Metadata context is required.",
            actionable_issue_count=len(
                actionable_issues
            ),
            final_status = "metadata_required",
        )

    if needs_knowledge:
        return ReviewRouteDecision(
            route=ReviewRoute.KNOWLEDGE_REQUIRED,
            reason="Knowledge context is required.",
            actionable_issue_count=len(
                actionable_issues
            ),
            final_status = "knowledge_required",
        )
        
    if has_context_action:
        return ReviewRouteDecision(
            route=ReviewRoute.CONTEXT_REQUIRED,
            reason="Additional context is required.",
            actionable_issue_count=len(
                actionable_issues
            ),
            final_status = "context_required",
        )
        
    can_auto_fix_all = all(
        _read_action(issue)
        == IssueAction.AUTO_FIX.value
        and bool(issue.get("auto_fixable"))
        for issue in actionable_issues
    )
    
    if can_auto_fix_all:
        return ReviewRouteDecision(
            route=ReviewRoute.AUTO_FIX,
            reason=(
                "All actionable issues "
                "support automatic fixing."
            ),
            actionable_issue_count=len(
                actionable_issues
            ),
            final_status = None,
        )


    return ReviewRouteDecision(
        route=ReviewRoute.HUMAN_REVIEW,
        reason=(
            "At least one issue cannot be "
            "safely fixed automatically."
        ),
        actionable_issue_count=len(
            actionable_issues
        ),
        final_status = "need_human_confirm",
    )