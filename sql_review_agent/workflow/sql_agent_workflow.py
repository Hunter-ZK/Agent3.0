from dataclasses import dataclass, field
from typing import Any

from sql_review_agent.schemas.responses import SQLExplainResponse, SQLFixResponse, SQLReviewResponse

from sql_review_agent.services.sql_critic_service import SQLCriticResponse


from uuid import uuid4

from sql_review_agent.engine.sql_review_engine import SQLReviewEngine
from sql_review_agent.schemas.requests import SQLExplainRequest, SQLFixRequest, SQLReviewRequest

from sql_review_agent.services.sql_critic_service import  SQLCriticResponse




@dataclass
class SQLAgentWorkflowResult:
    success: bool
    trace_id: str
    final_status: str

    explain_response: SQLExplainResponse | None = None
    review_response: SQLReviewResponse | None = None
    fix_response: SQLFixResponse | None = None
    re_review_response: SQLReviewResponse | None = None

    critic_response: SQLCriticResponse | None = None

    route_history: list[str] = field(default_factory=list)
    error_message: str|None = None



class SQLAgentWorkflow:

    METADATA_BLOCKING_TYPES = {
        "metadata_not_found",
        "table_not_found",
        "column_not_found",
        "unknown_table",
        "unknown_column",
    }
    
    def __init__(self, engine: SQLReviewEngine, max_retries: int = 1):
        self.engine = engine
        self.max_retries = max_retries

    @staticmethod
    def _get_route_signals(explain_response) -> dict:
        route_signals = getattr(explain_response, "route_signals", None)

        if not isinstance(route_signals, dict):
            return {}
        
        return route_signals
    
    @classmethod
    def _has_blocking_metadata_issue(
        cls,
        review_response: SQLReviewResponse,
    ) -> bool:
        for issue in review_response.issues or []:
            if not isinstance(issue, dict):
                continue

            issue_type = (
                issue.get("type")
                or issue.get("code")
                or issue.get("rule_id")
                or ""
            )

            if issue_type.lower() in cls.METADATA_BLOCKING_TYPES:
                return True

        return False

    def run(self, sql: str, file_path: str = "<memory>") -> SQLAgentWorkflowResult:
        trace_id = str(uuid4())
        route_history: list[str] = []

        explain_response = self.engine.explain(
            SQLExplainRequest(sql=sql, file_path=file_path, trace_id=trace_id)
        )

        route_history.append("explain")

        if not explain_response.success:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="explain_failed",
                explain_response=explain_response,
                route_history=route_history,
                error_message=explain_response.error_message,
            )
        
        route_signals = self._get_route_signals(explain_response)

        need_review = route_signals.get("need_review",True)
        can_auto_fix = route_signals.get("can_auto_fix", True)
        need_metadata = route_signals.get("need_metadata", False)
        need_rag = route_signals.get("need_rag", False)
        need_human_confirm = route_signals.get(
            "need_human_confirm",
            False,
        )




        if not need_review:
            return SQLAgentWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status="explained",
                explain_response=explain_response,
                route_history=route_history
            )
        
        review_response = self.engine.review(
            SQLReviewRequest(sql=sql, file_path=file_path, trace_id=trace_id)
        )
        route_history.append("review")


        if not review_response.success:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="review_failed",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=review_response.error_message,
            )
        

        if need_metadata:
            route_history.append("metadata_checked")


        if review_response.issue_count == 0:
            return SQLAgentWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status="no_issue",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )
        

        if need_rag:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="knowledge_required",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=(
                    "The review requires knowledge retrieval, "
                    "but RAG is not implemented."
                ),
            )

        if self._has_blocking_metadata_issue(review_response):
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="metadata_required",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=(
                    "Required table or column metadata was not found."
                ),
            )

        if need_human_confirm or can_auto_fix is not True:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="need_human_confirm",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        retry_count = 0
        critic_response = None

        while True:


            fix_response = self.engine.fix(
                SQLFixRequest(sql=sql, file_path=file_path, trace_id=trace_id, retry_count=retry_count,)
            )
            route_history.append("fix" if retry_count == 0 else f"fix_retry_{retry_count}")

            re_review_response = None

            if fix_response.success and fix_response.fixed_sql:
                re_review_response = self.engine.review(
                    SQLReviewRequest(
                        sql = fix_response.fixed_sql,
                        file_path=file_path,
                        trace_id=trace_id,
                    )
                )
            route_history.append("re_review" if retry_count == 0 else f"re_review_retry_{retry_count}")

            critic_response = self.engine.critique(
                review_response = review_response,
                fix_response = fix_response,
                re_review_response=re_review_response,
                trace_id=trace_id,
            )
            route_history.append("critic")

            if critic_response.passed:
                return SQLAgentWorkflowResult(
                    success=True,
                    trace_id=trace_id,
                    final_status="fix_verified",
                    explain_response=explain_response,
                    review_response=review_response,
                    fix_response=fix_response,
                    re_review_response=re_review_response,
                    critic_response=critic_response,
                    route_history=route_history,
                )
            
            can_retry = (
                critic_response.need_retry and retry_count < self.max_retries
            )
    
            if not can_retry:
                return SQLAgentWorkflowResult(
                    success=False,
                    trace_id=trace_id,
                    final_status="need_human_confirm",
                    explain_response=explain_response,
                    review_response=review_response,
                    fix_response=fix_response,
                    re_review_response=re_review_response,
                    critic_response=critic_response,
                    route_history=route_history,
                )

            retry_count += 1

