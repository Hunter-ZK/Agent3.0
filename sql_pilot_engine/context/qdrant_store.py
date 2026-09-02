"""
Qdrant 的 VectorStore 适配实现。

【架构位置】
ContextDocument
    -> EmbeddingProvider
    -> QdrantVectorStore.add()

User Question
    -> EmbeddingProvider
    -> QdrantVectorStore.search()
    -> RetrievedDocument
    -> KnowledgeRetriever / VerifiedSQLRetriever

【为什么放在 Context 层】
Qdrant 是 Knowledge Retrieval 的基础设施实现，不是 Semantic Truth 或业务事实库。
SemanticModel / Physical Metadata 仍由各自结构化存储负责，不能因为“都能检索”就迁入 Vector DB。

【边界】
- 本类只处理 collection、vector、payload 的存取，不决定哪些文档属于业务知识或 Verified SQL；
- Embedding 算法通过 Protocol 注入；
- 默认 ``:memory:`` client 主要服务开发/测试，生产连接配置应由 Composition Root 注入；
- search score 是检索排序信号，不是事实置信度。
"""

from __future__ import annotations

from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from sql_pilot_engine.context.embedding import EmbeddingProvider
from sql_pilot_engine.context.models import (
    ContextDocument,
    ContextDocumentKind,
    RetrievedDocument,
)


class QdrantVectorStore:
    """使用 Qdrant 实现 VectorStore Protocol 的基础设施适配器。"""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        collection_name: str = "agent3_context",
        client: QdrantClient | None = None,
    ) -> None:
        # Provider 决定向量维度，collection 必须用同一个维度创建。
        self.embedding_provider = embedding_provider
        self.collection_name = collection_name

        # 没有显式注入 client 时使用内存 Qdrant，使本地 Demo/Tests 不依赖外部服务。
        self.client = client or QdrantClient(":memory:")
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """
        确保目标 collection 存在。

        已存在时不重建，避免清空已有 Context Documents；新建时使用 COSINE，因为 Embedding
        检索关注向量方向相似度。collection 生命周期只属于存储适配器，不属于 Retriever。
        """

        if self.client.collection_exists(
            self.collection_name
        ):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.embedding_provider.dimensions,
                distance=Distance.COSINE,
            ),
        )

    def add(
        self,
        documents: list[ContextDocument],
    ) -> None:
        """
        对文档正文生成 Embedding，并以 Qdrant Point 写入 collection。

        payload 保存完整 ContextDocument Contract 所需字段，search 时可以无损重建 Domain DTO。
        Point id 使用独立 UUID，而 document_id 仍保存在 payload 中作为业务层稳定身份。
        """

        points: list[PointStruct] = []

        for document in documents:
            vector = self.embedding_provider.embed(
                document.text
            )

            points.append(
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "document_id": document.document_id,
                        "kind": document.kind.value,
                        "text": document.text,
                        "metadata": dict(document.metadata),
                    },
                )
            )

        # wait=True 保证方法返回时 upsert 已完成，便于紧接着 search 的测试/调用获得一致结果。
        self.client.upsert(
            collection_name=self.collection_name,
            wait=True,
            points=points,
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[RetrievedDocument]:
        """
        对查询文本向量化并返回 top_k 个 RetrievedDocument。

        本层不按 ContextDocumentKind 过滤；类型过滤由 KnowledgeRetriever / VerifiedSQLRetriever
        负责，这样 VectorStore 保持通用存储职责。
        """

        vector = self.embedding_provider.embed(query)

        points = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            with_payload=True,
            limit=top_k,
        ).points

        results: list[RetrievedDocument] = []

        for point in points:
            # Qdrant payload 是外部存储边界，因此这里显式恢复类型，而不是把裸 dict 泄漏给上层。
            payload = point.payload or {}

            document = ContextDocument(
                document_id=str(payload["document_id"]),
                kind=ContextDocumentKind(payload["kind"]),
                text=str(payload["text"]),
                metadata=dict(payload.get("metadata", {})),
            )

            results.append(
                RetrievedDocument(
                    document=document,
                    score=float(point.score),
                )
            )

        return results
