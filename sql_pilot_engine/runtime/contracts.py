from __future__ import annotations

from typing import Protocol


class CheckpointProvider(Protocol):
    """
    Runtime checkpoint abstraction.

    Runtime 不关心具体存储。

    可以是:
    - Memory
    - SQLite
    - PostgreSQL
    """

    def get_checkpointer(self):
        """
        返回 LangGraph checkpointer
        """
        ...


class RuntimeState(Protocol):
    """
    Agent Runtime State Contract.

    不定义具体业务字段。

    Capability 自己扩展。
    """
    pass