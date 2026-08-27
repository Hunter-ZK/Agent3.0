from __future__ import annotations

from sql_pilot_engine.llm.transport import (
    OpenAICompatibleTransport,
)

from sql_pilot_engine.config.llm import (
    LLMRequestConfig,
)

class DeepSeekTextGenerationModel:
    """
    DeepSeek 的文本生成 Adapter。

    TextGenerationModel 的实现。

    不负责：
    - API 配置解析
    - OpenAI Client 生命周期
    - Provider 错误转换
    """

    def __init__(
        self,
        *,
        transport: (
            OpenAICompatibleTransport
        ),
        request_config: (
            LLMRequestConfig
        ),
    ) -> None:
        
        self._transport = transport
        self._request_config = (
            request_config
        )

    def generate(
        self,
        prompt: str,
    ) -> str:
        
        if not prompt.strip():
            raise ValueError(
                "prompt must not be empty"
            )
            
        return (
            self._transport.complete(
                messages=(
                    {
                        "role":"user",
                        "content":prompt,
                    },
                ),
                request_config=self._request_config,
            )
        )