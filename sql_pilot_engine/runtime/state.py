from __future__ import annotations

from typing_extensions import (
    NotRequired,
    TypedDict,
)

from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)


class QueryAgentState(TypedDict):

    # 初始输入
    question: str

    # 配置
    dialect: NotRequired[str]

    # Context Intelligence
    semantic_context: NotRequired[str]
    query_context: NotRequired[
        QueryContext
    ]

    # Planning
    query_plan: NotRequired[
        QueryPlan
    ]

    # Generation
    generated_sql: NotRequired[
        str
    ]

    # Validation
    trusted_sql: NotRequired[str]
    validation_status: NotRequired[str]

    # 最终状态
    success: NotRequired[bool]
    error_message: NotRequired[
        str | None
    ]