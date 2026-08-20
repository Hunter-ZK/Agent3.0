from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class LLMUseCase(
    str,
    Enum,
):
    """
    Agent3.0 对模型能力的用途声明。

    Capability 只声明：
        “我要做什么”

    而不是声明：
        “我要调用 DeepSeek 哪个模型”
    """

    INTENT_ROUTING = "intent_routing"

    QUERY_PLANNING = "query_planning"

    SQL_GENERATION = "sql_generation"

    SQL_REVIEW = "sql_review"

    SEMANTIC_VALIDATION = (
        "semantic_validation"
    )

    KNOWLEDGE_QA = "knowledge_qa"


@dataclass(
    frozen=True,
    slots=True,
)
class LLMModelSpec:
    """
    一个实际可调用模型的配置描述。

    provider:
        模型服务提供方，例如 deepseek / private。

    model:
        Provider 中的真实模型名称。
    """

    provider: str

    model: str


@dataclass(
    frozen=True,
    slots=True,
)
class LLMRoutingConfig:
    """
    LLM Use Case → Model 的集中路由配置。

    这里只保存配置，不负责真正调用模型。
    """

    routes: Mapping[
        LLMUseCase,
        LLMModelSpec,
    ]

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "routes",
            MappingProxyType(
                dict(self.routes)
            ),
        )

    def resolve(
        self,
        use_case: LLMUseCase,
    ) -> LLMModelSpec:
        try:
            return self.routes[
                use_case
            ]

        except KeyError as exc:
            raise KeyError(
                "No LLM route configured "
                f"for use_case={use_case.value!r}"
            ) from exc