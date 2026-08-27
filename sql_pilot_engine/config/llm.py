from __future__ import annotations

import os

from dataclasses import dataclass

from dotenv import load_dotenv

from sql_pilot_engine.llm.errors import (
    LLMAPIError,
)


@dataclass(
    frozen=True,
    slots=True,
)
class LLMProviderConfig:
    """
    Provider 连接配置。
    """

    name: str

    api_key: str

    base_url: str

    model: str

    timeout_seconds: float


@dataclass(
    frozen=True,
    slots=True,
)
class LLMRequestConfig:
    """
    一类 LLM Request 的生成参数。

    不包含：
    - Provider
    - Prompt
    - JSON Schema
    """

    temperature: float

    max_tokens: int | None


@dataclass(
    frozen=True,
    slots=True,
)
class LLMSettings:
    """
    Agent3.0 当前完整 LLM 配置。
    """

    provider: LLMProviderConfig

    text_request: LLMRequestConfig

    structured_request: LLMRequestConfig


def _read_float(
    name: str,
    default: float,
) -> float:

    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        return float(raw)

    except ValueError as error:
        raise ValueError(
            f"{name} must be a float, "
            f"got {raw!r}"
        ) from error


def _read_int(
    name: str,
    default: int,
) -> int:

    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        return int(raw)

    except ValueError as error:
        raise ValueError(
            f"{name} must be an integer, "
            f"got {raw!r}"
        ) from error


def load_deepseek_settings(
) -> LLMSettings:

    load_dotenv()

    api_key = os.getenv(
        "DEEPSEEK_API_KEY"
    )

    if not api_key:
        raise LLMAPIError(
            "未配置 DEEPSEEK_API_KEY。"
        )

    provider = LLMProviderConfig(
        name="deepseek",

        api_key=api_key,

        base_url=os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com",
        ),

        model=os.getenv(
            "DEEPSEEK_MODEL",
            "deepseek-chat",
        ),

        timeout_seconds=_read_float(
            "AGENT3_LLM_TIMEOUT_SECONDS",
            60.0,
        ),
    )

    text_request = LLMRequestConfig(
        temperature=_read_float(
            "AGENT3_LLM_TEXT_TEMPERATURE",
            0.0,
        ),

        max_tokens=_read_int(
            "AGENT3_LLM_TEXT_MAX_TOKENS",
            4096,
        ),
    )

    structured_request = (
        LLMRequestConfig(
            temperature=_read_float(
                "AGENT3_LLM_STRUCTURED_TEMPERATURE",
                0.0,
            ),

            max_tokens=_read_int(
                "AGENT3_LLM_STRUCTURED_MAX_TOKENS",
                4096,
            ),
        )
    )

    return LLMSettings(
        provider=provider,
        text_request=text_request,
        structured_request=(
            structured_request
        ),
    )