from __future__ import annotations

from collections.abc import Sequence

from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)

from sql_pilot_engine.config.llm import (
    LLMProviderConfig,
    LLMRequestConfig,
)

from sql_pilot_engine.llm.errors import (
    LLMAPIError,
    LLMResponseParseError,
)

    
class OpenAICompatibleTransport:
    """
    OpenAI-compatible LLM
    的唯一底层 Transport。

    职责：

    messages
        ↓
    provider API
        ↓
    raw text

    不负责：
    - Planner Prompt
    - SQL Review
    - JSON Schema 业务 Contract
    - SQL Parsing
    - Agent Routing
    """
    
    def __init__(
        self,
        config: LLMProviderConfig,
    ) -> None:
        
        self._config = config
        
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )
        
    def complete(
        self,
        *,
        messages: Sequence[
            dict[str, str]
        ],
        request_config: LLMProviderConfig,
        response_format: (
            dict[str, Any] | None
        ) = None,
    ) -> str:
        
        request: dict[str, Any,] = {
            "model" : (
                self._config.model
            ),
            "messages": list(
                messages
            ),
            "temperature": (
                request_config.temperature
            ),
        }
        
        if response_format is not None:
            request["response_format"] = response_format
            
        if request_config.max_tokens is not None:
            request["max_tokens"] = request_config.max_tokens
            
        try:
            response = self._client.chat.completions.create(**request)
        
        except (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
        ) as error:
            raise LLMAPIError(str(error)) from error
        
        except Exception as error:
            raise LLMAPIError(str(error)) from error
        
        
        content = response.choices[0].message.content
        
        if not content:
            raise LLMResponseParseError(
                "LLM 返回内容为空"
            )
            
        return content.strip()
