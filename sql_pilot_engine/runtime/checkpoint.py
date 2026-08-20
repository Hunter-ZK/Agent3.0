from __future__ import annotations

from typing import (
    Protocol,
    runtime_checkable,
)

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)


@runtime_checkable
class CheckpointStore(Protocol):
    """
    Shared Agent Runtime 的 Checkpoint 存储契约。

    Runtime 只依赖这个协议，不感知底层具体实现。

    当前实现：
    - MemoryCheckpointStore
    - SQLiteCheckpointStore

    未来即使替换为 PostgreSQL，
    QueryAgentGraph 也不应该因此修改。
    """

    def get_backend(
        self,
    ) -> BaseCheckpointSaver:
        """
        返回 LangGraph 可接受的 Checkpointer。
        """
        ...