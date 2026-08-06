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
    
    

def _read_action(
    issue: dict[str, Any],
) -> str:
    
    action = issue.get("action")
    
    if isinstance(action, IssueAction):
        return action.value
    
    if isinstance(action, str):
        return action
    
    return IssueAction.HUMAN_REVIEW


def decide_review_route(
    response: SQLReviewResponse,
) -> ReviewRouteDecision:
    
    if not response.success:
        raise ValueError(
            "Cannot route a failed review response."
        )
        
    actionable_issues = [
        issue 
        for issue in response.issues
        if _read_action(issue)
        != IssueAction.IGNORE.value
    ]
    
    if not actionable_issues:
        return ReviewRouteDecision(
            route=ReviewRoute.COMPLETE,
            reason=(
                "No actionable issues remain."
            ),
            actionable_issue_count=0,
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
        )
        
    if needs_metadata:
        return ReviewRouteDecision(
            route=ReviewRoute.METADATA_REQUIRED,
            reason="Metadata context is required.",
            actionable_issue_count=len(
                actionable_issues
            ),
        )

    if needs_knowledge:
        return ReviewRouteDecision(
            route=ReviewRoute.KNOWLEDGE_REQUIRED,
            reason="Knowledge context is required.",
            actionable_issue_count=len(
                actionable_issues
            ),
        )
        
    if has_context_action:
        return ReviewRouteDecision(
            route=ReviewRoute.CONTEXT_REQUIRED,
            reason="Additional context is required.",
            actionable_issue_count=len(
                actionable_issues
            ),
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
    )