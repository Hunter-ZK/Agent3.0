from dataclasses import dataclass, field
from typing import Any

from sql_review_agent.schemas.responses import SQLExplainResponse, SQLFixResponse, SQLReviewResponse

from sql_review_agent.agents.sql_critic_agent import SQLCriticResponse

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


from uuid import uuid4

from sql_review_agent.engine.sql_review_engine import SQLReviewEngine
from sql_review_agent.schemas.requests import SQLExplainRequest, SQLFixRequest, SQLReviewRequest

from sql_review_agent.agents.sql_critic_agent import SQLCriticAgent, SQLCriticResponse

class SQLAgentWorkflow:

    def __init__(self, engine: SQLReviewEngine, critic_agent, max_retries: int = 1):
        self.engine = engine
        self.critic_agent = critic_agent
        self.max_retries = max_retries


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

        fix_response = self.engine.fix(
            SQLFixRequest(sql=sql, file_path=file_path, trace_id=trace_id, retry_count=retry_count,)
        )
        route_history.append("fix")

        while True:

            critic_response = self.critic_agent.critique(
                orignal_sql = sql,
                review_response = review_response,
                fix_response = fix_response,
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
