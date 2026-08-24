from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from sql_pilot_engine.context.builder import (
        QueryContext,
    )


@dataclass
class SQLExecutionContext:
    """
    SQL Core 内部一次执行的共享运行上下文。

    注意：
    QueryContext 是当前用户任务的业务上下文；
    SQLExecutionContext 是 SQL Core 的执行参数容器。

    SQLExecutionContext 不重新生成 QueryContext，
    只保存上游传入的同一个对象引用。
    """

    sql: str

    file_path: str = "<memory>"

    mode: str = "prod"

    dialect: str = "maxcompute"

    categories: set[str] | None = None

    enable_metadata: bool = False

    metadata_provider: Any | None = None

    enable_llm: bool = False

    llm_provider: str = "mock"

    query_context: QueryContext | None = None

    fix_sql: bool = False

    fix_provider: str = "auto"

    trace_id: str = field(
        default_factory=lambda: str(
            uuid4()
        )
    )

    retry_count: int = 0

    retrieved_docs: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    critic_feedback: list[
        str
    ] = field(
        default_factory=list
    )