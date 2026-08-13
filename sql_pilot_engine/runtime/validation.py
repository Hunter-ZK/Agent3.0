from __future__ import annotations

from dataclasses import dataclass 
from typing import Protocol


@dataclass(frozen=True)
class TrustedSQLResult:
    accepted: bool
    
    original_sql: str
    final_sql: str | None
    
    status: str
    issue_count: int = 0
    
    

class SQLValidationPort(Protocol):
    
    def validate(
        self,
        *,
        sql: str,
        dialect: str,
    ) -> TrustedSQLResult:
        ...
        
        
        