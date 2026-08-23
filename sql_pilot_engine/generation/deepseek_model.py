from dataclasses import dataclass
import os
from openai import OpenAI

from dotenv import load_dotenv

import logging
import time


load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class DeepSeekTextGenerationModel:
    """DeepSeek OpenAI-compatible LLM Client.

    只负责一件事：
    prompt string → model output string

    不负责：
    - 构造业务 prompt
    - 解析 JSON
    - 生成 SQLExplainResponse
    - 做 Agent 路由
    """

    api_key: str
    base_url: str
    model: str = "deepseek-chat"
    temperature: float = 0.0
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "DeepSeekTextGenerationModel":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL")
        model = os.getenv("DEEPSEEK_MODEL","deepseek-chat")

        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        if not base_url:
            raise ValueError("DEEPSEEK_BASE_URL is required")
        
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )


    def generate(self, prompt: str) -> str:
        """执行一次通用文本生成。

        这里只负责：
        prompt -> model output string

        不关心调用方是在：
        - 做 Query Planning
        - 生成 SQL
        - Explain SQL
        - 修复 JSON
        """

        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        try:
            start = time.perf_counter()

            logger.info(
                "llm.request provider=deepseek model=%s prompt_chars=%d",
                self.model,
                len(prompt),
            )

            response = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {
                        "role":"user",
                        "content":prompt,
                    }
                ]
            )

            content = response.choices[0].message.content

            if not content:
                raise ValueError(
                    "DeepSeek returned empty content"
                )

            elapsed_ms = int(
                (time.perf_counter() - start) * 1000
            )

            logger.info(
                "llm.response provider=deepseek model=%s "
                "response_chars=%d elapsed_ms=%d",
                self.model,
                len(content),
                elapsed_ms,
            )
        except Exception:
            logger.exception(
                "llm.error provider=deepseek model=%s",
                self.model,
            )
            raise


        return content.strip()
    
