from __future__ import annotations

from enum import Enum


class RuntimeTerminalStatus(
    str,
    Enum,
):
    """
    Agent Runtime 的统一业务终态。

    注意：
    这是 Runtime / Capability Workflow 层面的终态，
    不是某个具体 Validator 内部的 Issue 状态。

    F1 只冻结 Contract。
    具体 DENY 路由在 Capability 2 / F5 阶段接入。
    """

    PASS = "pass"

    DENY = "deny"

    RETRY = "retry"

    CLARIFY = "clarify"

    HITL = "hitl"