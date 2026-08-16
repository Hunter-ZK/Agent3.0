from sql_pilot_engine.runtime.validation import TrustedSQLResult

from sql_pilot_engine.workflow.sql_agent_workflow import SQLAgentWorkflow

class WorkflowSQLValidationAdapter:

    def __init__(
        self,
        workflow: SQLAgentWorkflow,
    ) -> None:
        self.workflow = workflow


    def validate(
        self,
        *,
        sql: str,
        dialect: str,
    ) -> TrustedSQLResult:

        workflow_result = self.workflow.run(
            sql=sql,
        )

        if workflow_result.success:

            final_sql = sql

            if (workflow_result.fix_response is not None and workflow_result.fix_response.fixed_sql):
                final_sql = workflow_result.fix_response.fixed_sql

            return TrustedSQLResult(
                accepted=True,
                original_sql=sql,
                final_sql=final_sql,
                status=workflow_result.final_status,
            )
        