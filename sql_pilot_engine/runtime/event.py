from __future__ import annotations

from enum import Enum

from dataclasses import (
    dataclass,
    field,
)

from datetime import (
    datetime,
    timezone,
)

from collections.abc import Mapping

class RuntimeEventType(
    str,
    Enum,
):
    """
    Shared Agent Runtime 的事件类型契约。

    """

    USER_MESSAGE = "user_message"

    PLAN = "plan"

    TOOL_CALL = "tool_call"

    TOOL_RESULT = "tool_result"

    VALIDATION = "validation"

    APPROVAL = "approval"

    AGENT_RESULT = "agent_result"

@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeEvent:
    """
    Agent Runtime 的统一事件契约。

    Event 描述：

        在哪个 Capability
        的哪个 Thread / Turn
        的哪个 Stage
        发生了什么。

    Event 不属于 QueryAgentState，
    也不参与 LangGraph Checkpoint。
    """

    event_type: RuntimeEventType

    capability: str

    thread_id: str

    turn_id: str

    stage: str

    data: Mapping[
        str,
        object,
    ] = field(
        default_factory=dict
    )

    occurred_at: datetime = field(
        default_factory=lambda:(
            datetime.now(
                timezone.utc
            )
        )
    )

    
    def __post_init__(
        self,
    ) -> None:

        if not self.capability.strip():
            raise ValueError(
                "capability cannot be empty"
            )

        if not self.thread_id.strip():
            raise ValueError(
                "thread_id cannot be empty"
            )

        if not self.turn_id.strip():
            raise ValueError(
                "turn_id cannot be empty"
            )

        if not self.stage.strip():
            raise ValueError(
                "stage cannot be empty"
            )

        if (
            self.occurred_at.tzinfo
            is None
        ):
            raise ValueError(
                "occurred_at must be "
                "timezone-aware"
            )