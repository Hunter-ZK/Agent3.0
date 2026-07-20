# sql_review_agent/core/execution_context.py

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from sql_review_agent.schemas.requests import SQLFixRequest,SQLReviewRequest


@dataclass
class ReviewExecutionContext:
    """SQL Review/Fix 的内部执行上下文。

    Request 是外部调用契约；
    ExecutionContext 是 Engine 进入内部服务后的执行状态包；
    Response 是外部返回契约。

    后续 RAG、Critic、Trace、Retry、Human Feedback 都会优先挂在 Context
    或未来 Agent State 上，而不是继续塞进函数长参数。
    """
    sql: str
    file_path: str = "<memory>"
    mode: str = "prod"
    dialect: str = "maxcompute"
    categories: set[str]|None = None

    enable_metadata: bool = False
    metadata_provider: Any | None = None

    enable_llm: bool = False
    llm_provider: str = "mock"

    fix_sql: bool = False
    fix_provider: str = "auto"

    trace_id: str = field(default_factory=lambda: str(uuid4()))
    retry_count: int = 0
    retrieved_docs: list[dict[str, Any]] = field(default_factory=list)

    critic_feedback: list[str] = field(default_factory=list)


    @classmethod
    def from_review_request(cls, request: SQLReviewRequest) -> "ReviewExecutionContext":
        # TODO 1:
        # 把 SQLReviewRequest 转成 ReviewExecutionContext。
        # 注意：
        # - fix_sql 必须是 False
        # - fix_provider 可以保留默认值
        # - metadata_provider / enable_metadata / enable_llm / llm_provider 都要带过去

        return cls(
            sql = request.sql,
            file_path = request.file_path,
            mode = request.mode,
            dialect = request.dialect,
            categories = request.categories,
            enable_metadata=request.enable_metadata,
            metadata_provider=request.metadata_provider,
            enable_llm=request.enable_llm,
            llm_provider=request.llm_provider,
            fix_sql = False,
            trace_id = request.trace_id or str(uuid4()),
        )

        
    @classmethod
    def from_fix_request(cls, request: SQLFixRequest) -> "ReviewExecutionContext":
        # TODO 2:
        # 把 SQLFixRequest 转成 ReviewExecutionContext。
        # 注意：
        # - fix_sql 必须是 True
        # - fix_provider 必须来自 request.fix_provider
        # - 其他字段和 review request 类似
        return cls(
            sql = request.sql,
            file_path = request.file_path,
            mode = request.mode,
            dialect = request.dialect,
            categories = request.categories,
            enable_metadata=request.enable_metadata,
            metadata_provider=request.metadata_provider,
            enable_llm=request.enable_llm,
            llm_provider=request.llm_provider,
            fix_sql=True,
            fix_provider=request.fix_provider,
            trace_id = request.trace_id or str(uuid4()),
            critic_feedback=request.critic_feedback,
            retry_count=request.retry_count,
        )
