from __future__ import annotations

from typing import Protocol


class LLMAdapter(Protocol):
    
    def generate(
        self,
        *,
        prompt: str,
    ) -> str:
        ...
        
    def genearte_json(
        self,
        *,
        prompt: str,
    ) -> dict:
        ...
        
    def embed(
        self,
        *,
        text: str,
    ) -> list[float]:
        ...