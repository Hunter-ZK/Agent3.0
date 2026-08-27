from __future__ import annotations

from typing import Protocol

from sql_pilot_engine.context.builder import (
    QueryContext,
)


class TrustedSQLWorkflowResultView(Protocol):
    """
    Agent Runtime 对 Trusted SQL Workflow
    Result 真正依赖的最小 Contract。
    """

    success: bool

    final_status: str

    trusted_sql: str | None

    error_message: str | None
    
    missing_context: tuple[str, ...] 


class TrustedSQLWorkflowPort(Protocol):
    """
    Agent Runtime 对 SQL 可信化子工作流
    所依赖的最小接口。

    正式实现：
        TrustedSQLWorkflow

    测试：
        Fake / Stub TrustedSQLWorkflow
    """

    def run(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
        query_context: QueryContext | None = None,
    ) -> TrustedSQLWorkflowResultView:
        ...