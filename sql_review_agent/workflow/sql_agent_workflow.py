from dataclasses import dataclass, field
from typing import Any

from sql_review_agent.schemas.responses import SQLExplainResponse, SQLFixResponse, SQLReviewResponse

from sql_review_agent.agents.sql_critic_agent import SQLCriticResponse


from uuid import uuid4

from sql_review_agent.engine.sql_review_engine import SQLReviewEngine
from sql_review_agent.schemas.requests import SQLExplainRequest, SQLFixRequest, SQLReviewRequest

from sql_review_agent.agents.sql_critic_agent import  SQLCriticResponse, SQLCriticAgent

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

    def __init__(self, engine: SQLReviewEngine, critic_agent: SQLCriticAgent, max_retries: int = 1):
        self.engine = engine
        self.critic_agent = critic_agent
        self.max_retries = max_retries

    @staticmethod
    def _get_route_signals(explain_response) -> dict:
        route_signals = getattr(explain_response, "route_signals", None)

        if not isinstance(route_signals, dict):
            return {}
        
        return route_signals
    

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

        if not need_review:
            return SQLAgentWorkflowResult(
                success=False,
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
        
        if review_response.issue_count == 0:
            return SQLAgentWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status="no_issue",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )
        
        retry_count = 0
        critic_response = None

        can_auto_fix = route_signals.get("can_auto_fix", False)
        need_metadata = route_signals.get("need_metadata", False)
        need_rag = route_signals.get("need_rag", False)
        need_human_confirm = route_signals.get(
            "need_human_confirm",
            False,
        )

        if need_metadata or need_rag:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="context_required",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
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

        fix_response = self.engine.fix(
            SQLFixRequest(sql=sql, file_path=file_path, trace_id=trace_id, retry_count=retry_count,)
        )
        route_history.append("fix")

        re_review_response = None

        if fix_response.success and fix_response.fixed_sql:
            re_review_response = self.engine.review(
                SQLReviewRequest(
                    sql = fix_response.fixed_sql,
                    file_path=file_path,
                    trace_id=trace_id,
                )
            )
            route_history.append("re_review")

        while True:

            critic_response = self.critic_agent.critique(
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

            fix_response = self.engine.fix(
                SQLFixRequest(
                    sql = sql,
                    file_path=file_path,
                    trace_id=trace_id,
                    retry_count=retry_count,
                    critic_feedback=critic_response.retry_instructions,
                )
            )

            route_history.append(f"fix_retry_{retry_count}")
