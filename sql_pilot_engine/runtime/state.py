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

from sql_pilot_engine.runtime.event import (
    RuntimeEventType,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
)
    

class QueryAgentState(TypedDict):
    """LangGraph Text-to-SQL Runtime State.

    State只保存节点之间需要共享的数据。

    节点本身仍然复用现有：
    - Retriever
    - Planner
    - Generator
    - Validation Workflow
    - Semantic Validator

    不在State里重新实现业务逻辑。
    """

    # ========================================================
    # Initial Input
    # ========================================================
    
    question: str

    dialect: NotRequired[str]

    session_context: NotRequired[
        tuple[str, ...]
    ]

    thread_id: str
    turn_id: str

    event_type: RuntimeEventType | None

    # ========================================================
    # Context Intelligence
    # ========================================================
    
    query_context: NotRequired[
        QueryContext | None
    ]

    # ========================================================
    # Planning
    # ========================================================
    
    query_plan: NotRequired[
        QueryPlan | None
    ]

    # Planner要求用户补充时填写。
    clarification_question: NotRequired[
        str | None
    ]

    missing_context: NotRequired[
        tuple[str, ...]
    ]

    clarification_reason: NotRequired[
        str
    ]

    # ========================================================
    # Human-in-the-loop
    # ========================================================

    clarification_round: NotRequired[int]

    max_clarification_rounds: NotRequired[int]
    
    # ========================================================
    # Schema Linking
    # ========================================================

    linked_schema: NotRequired[
        LinkedSchema | None
    ]

    linking_error_message: NotRequired[
        str | None
    ]
        

    # ========================================================
    # Generation
    # ========================================================
    
    generated_sql: NotRequired[
        str | None
    ]

    revision_feedback: NotRequired[
        tuple[str, ...]
    ]

    generation_attempt: NotRequired[int]

    max_semantic_retries: NotRequired[int]

    # ========================================================
    # SQL Validation
    # ========================================================

    candidate_sql: NotRequired[
        str | None
    ]

    validation_status: NotRequired[
        str | None
    ]

    validation_error_message: NotRequired[
        str | None
    ]

    # ========================================================
    # Semantic Validation
    # ========================================================

    semantic_validation_status: NotRequired[
        str | None
    ]

    semantic_missing_requirements: NotRequired[
        tuple[str, ...]
    ]

    semantic_issues: NotRequired[
        tuple[str, ...]
    ]


    # ========================================================
    # Final Result
    # ========================================================
    trusted_sql: NotRequired[
        str | None
    ]

    success: NotRequired[bool]

    error_message: NotRequired[
        str | None
    ]

    validation_error_message: (
        str | None
    )

        
