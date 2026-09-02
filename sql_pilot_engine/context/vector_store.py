"""
Context Intelligence 使用的 VectorStore Protocol。

【架构位置】
ContextDocument -> VectorStore.add()
User Question -> VectorStore.search() -> RetrievedDocument -> Retriever -> QueryContextBuilder

【为什么用 Protocol 而不是直接依赖 Qdrant】
上层 Retrieval 只需要“写入文档”和“按查询返回 Top-K”两个能力，不应该知道 collection、client、
向量距离算法等基础设施细节。QdrantVectorStore 是当前实现之一，本 Protocol 保持调用边界稳定。

【边界】
VectorStore 是检索基础设施，不是 Source of Truth。score 只表示召回排序信号，不能替代
Semantic Asset、Metadata 或 Deterministic Evidence。
"""

from __future__ import annotations

from typing import Protocol

from sql_pilot_engine.context.models import (
    ContextDocument,
    RetrievedDocument,
)


class VectorStore(Protocol):
    """Context Retrieval 所需的最小向量存储接口。"""

    def add(
        self,
        documents: list[ContextDocument],
    ) -> None:
        """把一批长期 Context Documents 写入检索存储。"""
        ...

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[RetrievedDocument]:
        """
        按 query 召回最相关的 top_k 文档。

        返回结果应保持相关性排序；具体 Embedding、距离函数与存储实现由 Adapter 自己负责。
        """
        ...
