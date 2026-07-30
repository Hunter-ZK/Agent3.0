from dataclasses import dataclass
import os
from openai import OpenAI

@dataclass
class DeepSeekLLMClient:
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
    def from_env(cls) -> "DeepSeekLLMClient":
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
    
    def complete(self, prompt: str) -> str:
        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        response = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise SQL analysis assistant. Return only valid JSON.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("DeepSeek returned empty content")
        
        return content
    