from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class SQLExecutionContext:
    """
    SQL Core 内部一次执行的共享上下文。

    Request:
        外部接口 DTO

    SQLExecutionContext:
        Engine 进入内部 Service 后使用的执行上下文

    Response:
        外部返回 DTO

    Core 不认识任何具体 Request 类型。
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