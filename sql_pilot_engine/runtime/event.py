from __future__ import annotations

from enum import Enum


class RuntimeEventType(
    str,
    Enum,
):
    """
    Shared Agent Runtime 的事件类型契约。

    F1 只冻结事件类型，
    暂不实现 Event Bus、Streaming 或事件持久化。
    """

    USER_MESSAGE = "user_message"

    PLAN = "plan"

    TOOL_CALL = "tool_call"

    TOOL_RESULT = "tool_result"

    VALIDATION = "validation"

    APPROVAL = "approval"

    AGENT_RESULT = "agent_result"