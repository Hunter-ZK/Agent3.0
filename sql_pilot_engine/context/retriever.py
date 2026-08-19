from __future__ import annotations

from sql_pilot_engine.context.models import (
    ContextDocumentKind,
    RetrievedDocument,
)

from sql_pilot_engine.context.vector_store import (
    VectorStore,
)


class KnowledgeRetriever:
    
    def __init__(
        self,
        vector_store: VectorStore,
    ) -> None:
        self.vector_store = vector_store
        
    def retrieve(
        self,
        question: str,
        *,
        top_k: int = 5,
    ) -> list[RetrievedDocument]:
        results = (
            self.vector_store.search(
                query=question,
                top_k=max(
                    top_k * 2,
                    top_k,
                ),
            )
        )
        
        knowledge_results =  [
            item
            for item in results
            if item.document.kind == ContextDocumentKind.BUSINESS_KNOWLEDGE
        ]
        
        return knowledge_results[:top_k]
        
class VerifiedSQLRetriever:
    
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
        
        results = (
            self.vector_store.search(
                question,
                top_k=max(top_k * 2, top_k),
            )
        )
        
        sql_results = [
            item
            for item in results
            if item.document.kind == ContextDocumentKind.VERIFIED_SQL
        ]
        
        return sql_results[:top_k]