from __future__ import annotations

from typing import (
    Any,
    Protocol,
)


class TextGenerationModel(
    Protocol
):
    """
    非结构化文本生成契约。

    适用于：
    - Query Planner
    - SQL Generator
    - 其他自然语言 / SQL 文本生成
    """
    
    def generate(
        self,
        prompt: str,
    ) -> str:
        ...

class StructuredGenerationModel(
    Protocol
):
    """
    结构化 JSON 生成契约。

    适用于：
    - Reviewer
    - Fixer
    - Explainer
    - Optimizer
    - 后续结构化 Semantic Validator
    """
    
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[
            str,
            Any,
        ],
    ) -> dict[str, Any]:
        ...