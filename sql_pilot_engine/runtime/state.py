from __future__ import annotations
from enum import Enum

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

from sql_pilot_engine.services.semantic_validation_service import (
    SemanticValidationResult,
)

from sql_pilot_engine.workflow.sql_agent_workflow import (
    SQLAgentWorkflowResult,
)




class AgentEventType(str, Enum):
    USER_MESSAGE = "user_message"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    VALIDATION = "validation"
    APPROVAL = "approval"
    RESULT = "result"
    
    
    

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

    thread_id: str | None
    turn_id: str | None
    event_type: AgentEventType | None

    # ========================================================
    # Context Intelligence
    # ========================================================
    
    semantic_context: NotRequired[str]
    query_context: NotRequired[
        QueryContext
    ]

    # ========================================================
    # Planning
    # ========================================================
    
    query_plan: NotRequired[
        QueryPlan
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
    # Generation
    # ========================================================
    
    generated_sql: NotRequired[
        str
    ]

    revision_feedback: NotRequired[
        tuple[str, ...]
    ]

    generation_attempt: NotRequired[int]

    max_semantic_retries: NotRequired[int]

    # ========================================================
    # SQL Validation
    # ========================================================
    
    validation_result: NotRequired[
        SQLAgentWorkflowResult
    ]
    
    candidate_sql: NotRequired[
        str | None
    ]

    validation_status: NotRequired[
        str | None
    ]

    # ========================================================
    # Semantic Validation
    # ========================================================
    
    semantic_result: NotRequired[
        SemanticValidationResult | None
    ]

    semantic_validation_status: NotRequired[
        str | None
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
    

    
