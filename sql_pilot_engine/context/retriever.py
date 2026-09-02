"""
针对同一 VectorStore 的两类任务级 Retriever。

【架构位置】
VectorStore.search()
    -> RetrievedDocument[*]
    -> KnowledgeRetriever      -> BUSINESS_KNOWLEDGE
    -> VerifiedSQLRetriever    -> VERIFIED_SQL
    -> QueryContextBuilder

【为什么不让 VectorStore 直接区分业务类型】
VectorStore 只负责“向量相似度 + 存取”；Retriever 才负责“本次任务需要哪一类知识”。
把 kind 过滤放在 Retriever 可以让 Qdrant/InMemory 等存储实现保持通用，也避免存储层理解业务用途。

【为什么先扩大召回再过滤】
同一个 collection 混合存放 Business Knowledge 与 Verified SQL。若直接 top_k=3 后再按 kind 过滤，
前三个结果可能全部属于另一类，导致目标类型召回不足。因此这里先取约 2 倍候选，再过滤截断。
"""

from __future__ import annotations

from sql_pilot_engine.context.models import (
    ContextDocumentKind,
    RetrievedDocument,
)
from sql_pilot_engine.context.vector_store import VectorStore


class KnowledgeRetriever:
    """从通用 VectorStore 中只返回 BUSINESS_KNOWLEDGE 文档。"""

    def __init__(
        self,
        vector_store: VectorStore,
    ) -> None:
        # 通过 Protocol 依赖存储能力，不耦合 Qdrant 具体实现。
        self.vector_store = vector_store

    def retrieve(
        self,
        question: str,
        *,
        top_k: int = 5,
    ) -> list[RetrievedDocument]:
        """
        召回与当前问题相关的业务知识。

        Retriever 不修改 score、不做业务正确性判断；它只按文档 kind 过滤 VectorStore 的排序结果。
        """

        results = self.vector_store.search(
            query=question,
            # collection 混合存储两种 kind，因此先扩大候选，降低过滤后数量不足的概率。
            top_k=max(top_k * 2, top_k),
        )

        knowledge_results = [
            item
            for item in results
            if item.document.kind == ContextDocumentKind.BUSINESS_KNOWLEDGE
        ]

        return knowledge_results[:top_k]


class VerifiedSQLRetriever:
    """从通用 VectorStore 中只返回已经标记为 VERIFIED_SQL 的示例。"""

    def __init__(
        self,
        vector_store: VectorStore,
    ) -> None:
        self.vector_store = vector_store

    def retrieve(
        self,
        question: str,
        *,
        top_k: int = 3,
    ) -> list[RetrievedDocument]:
        """
        召回与当前问题最相似的 Verified SQL 示例。

        “Verified”表示该文档资产已被确认可作为参考，不意味着召回到的 SQL 可以直接作为本次
        trusted_sql。Planner/Generator 仍必须结合当前 QueryContext、LinkedSchema 与 Trust Gate。
        """

        results = self.vector_store.search(
            question,
            top_k=max(top_k * 2, top_k),
        )

        sql_results = [
            item
            for item in results
            if item.document.kind == ContextDocumentKind.VERIFIED_SQL
        ]

        return sql_results[:top_k]
