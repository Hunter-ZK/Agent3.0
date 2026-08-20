from __future__ import annotations

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)
from langgraph.checkpoint.memory import (
    InMemorySaver,
)

from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)


class MemoryCheckpointStore:
    """
    进程内 Checkpoint 实现。

    主要用于：
    - 单元测试
    - 临时 Demo
    - 不需要跨进程恢复的开发场景

    正式 Runtime 不应把它作为默认持久化方案。
    """

    def __init__(
        self,
    ) -> None:
        self._backend = InMemorySaver()

    def get_backend(
        self,
    ) -> BaseCheckpointSaver:
        return self._backend