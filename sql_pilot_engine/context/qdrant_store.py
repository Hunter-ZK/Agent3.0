from __future__ import annotations

from uuid import uuid4

from qdrant_client import (
    QdrantClient,
)

from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from sql_pilot_engine.context.embedding import (
    EmbeddingProvider,
)

from sql_pilot_engine.context.models import (
    ContextDocument,
    ContextDocumentKind,
    RetrievedDocument,
)


class QdrantVectorStore:
    
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        collection_name: str = (
            "agent3_context"
        ),
        client: QdrantClient | None = None,
    ) -> None:
        
        self.embedding_provider = (
            embedding_provider
        )
        
        self.collection_name = (
            collection_name
        )
        
        self.client = (
            client
            or QdrantClient(":memory")
        )
        
    
    def _ensure_collection(
        self,
    ) -> None:
        
        if self.client.collection_exists(
            self.collection_name
        ):
            return
        
        self.client.create_collection(
            collection_name=(
                self.collection_name
            ),
            vectors_config = VectorParams(
                size=(
                    self.embedding_provider.dimensions
                ),
                distance=Distance.COSINE,
            ),
        )
        
    def add(
        self,
        documents: list[
            ContextDocument
        ],
    ) -> None:
        
        points: list[
            PointStruct
        ] = []
        
        for document in documents:
            
            vector = (
                self.embedding_provider.embed(document.text)
            )
            
            points.append(
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "document_id":(
                            document.document_id
                        ),
                        "kind":(
                            document.kind.value
                        ),
                        "text":(
                            document.text
                        ),
                        "metadata":dict(
                            document.metadata
                        ),
                    },
                )
            )
        
        self.client.upsert(
            collection_name=(
                self.collection_name
            ),
            wait=True,
            points=points,
        )
        
    
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[RetrievedDocument]:
        
        vector = (
            self.embedding_provider.embed(query)
        )
        
        points = (
            self.client.query_points(
                collection_name=(
                    self.collection_name
                ),
                query=vector,
                with_payload=True,
                limit=top_k,
            ).points
        )
        
        results: list[
            RetrievedDocument
        ] = []
        
        for point in points:
            
            payload = (
                point.payload or {}
            )
            
            document = ContextDocument(
                document_id=str(
                    payload["document_id"]
                ),
                kind=ContextDocumentKind(
                    payload["kind"]
                ),
                text=str(
                    payload["text"]
                ),
                metadata=dict(
                    payload.get(
                        "metadata",
                        {},
                    )
                ),
            )
            
            results.append(
                RetrievedDocument(
                    document=document,
                    score=float(
                        point.score
                    ),
                )
            )
        return results