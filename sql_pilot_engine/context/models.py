from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ContextDocumentKind(str, Enum):
    BUSINESS_KNOWLEDGE = "business_knowledge"
    VERIFIED_SQL = "verified_sql"
    

@dataclass(frozen=True)
class ContextDocument:
    document_id: str
    kind: ContextDocumentKind
    
    text: str
    
    metadata: Mapping[str, str]
    

@dataclass(frozen=True)
class RetrievedDocument:
    document: ContextDocument
    score: float