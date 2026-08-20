from __future__ import annotations

from typing import Protocol


class LLMAdapter(Protocol):
    """
    Agent3.0 模型抽象。

    Capability 不关心:
    - DeepSeek
    - OpenAI
    - Local Model
    """

    def generate(
        self,
        prompt: str,
    ) -> str:
        ...


    def generate_json(
        self,
        prompt: str,
    ) -> dict:
        ...


    def embed(
        self,
        text: str,
    ) -> list[float]:
        ...