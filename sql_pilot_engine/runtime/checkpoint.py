"""
Checkpoint factory.

Runtime only depends on checkpointer contract.
Storage implementation is selected outside workflow.
"""

from __future__ import annotations

from typing import Protocol

def CheckpointStore(Protocol):
    """
    Agent Runtime checkpoint contract.

    Runtime 只依赖这个协议，
    不关心底层使用 Memory / SQLite / PostgreSQL。
    """
    
    def get_backend(self):
        """
        返回 LangGraph 可接受的 checkpointer 实例。
        """
        ...