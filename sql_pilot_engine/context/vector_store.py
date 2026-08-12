
from __future__ import annotations

from typing import Protocol

from sql_pilot_engine.context.models import (
    ContextDocument,
    RetrievedDocument,
)


class VectorStore(Protocol):
    
    def add(
        self,
        documents: list[
            ContextDocument
        ],
    ) -> None:
        ...
        
        
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[
        RetrievedDocument
    ]:
        ...