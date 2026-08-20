from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)
from langgraph.checkpoint.sqlite import (
    SqliteSaver,
)


class SQLiteCheckpointStore:
    """
    基于 SQLite 的持久化 CheckpointStore。

    负责：
    - 打开独立 checkpoints.db
    - 持有 SQLite connection 生命周期
    - 将 SqliteSaver 暴露给 LangGraph

    不负责：
    - Metadata
    - Standards
    - Runtime 业务逻辑
    - Graph 编排
    """

    def __init__(
        self,
        database_path: str | Path,
    ) -> None:
        self._database_path = Path(
            database_path
        ).expanduser().resolve()

        self._database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._connection = sqlite3.connect(
            self._database_path,
            check_same_thread=False,
        )

        self._backend = SqliteSaver(
            self._connection
        )

    @property
    def database_path(
        self,
    ) -> Path:
        return self._database_path

    def get_backend(
        self,
    ) -> BaseCheckpointSaver:
        return self._backend

    def close(
        self,
    ) -> None:
        self._connection.close()