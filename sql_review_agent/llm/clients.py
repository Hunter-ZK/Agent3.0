# sql_review_agent/llm/clients.py

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from sql_review_agent.llm.errors import LLMAPIError, LLMResponseParseError


class BaseLLMClient(ABC):
    """LLM Client 抽象。"""

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    """用于测试和离线开发的 Mock LLM。"""

    def generate_json(self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]) -> dict[str, Any]:
        lower_system_prompt = system_prompt.lower()
        if "fixed_sql" in lower_system_prompt and "manual_notes" in lower_system_prompt:
            return self._generate_mock_fix_result(user_prompt)
        return self._generate_mock_review_result(user_prompt)

    def _generate_mock_review_result(self, user_prompt: str) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        lower_prompt = user_prompt.lower()

        if "sum(" in lower_prompt and "coalesce" not in lower_prompt and "nvl" not in lower_prompt:
            issues.append(
                {
                    "rule_id": "LLM_AGGREGATION_NULL_HANDLING_SUGGESTION",
                    "title": "聚合金额字段建议考虑空值处理",
                    "severity": "medium",
                    "message": "检测到聚合计算中可能未显式处理空值，建议确认金额字段是否可能为空。",
                    "suggestion": "如字段可能为空，可考虑使用 COALESCE 或 NVL 包裹金额字段。",
                    "evidence": "sum(...) has no null handling",
                    "category": "semantic",
                    "confidence": 0.7,
                }
            )

        if " join " in lower_prompt and " group by " in lower_prompt:
            issues.append(
                {
                    "rule_id": "LLM_JOIN_DUPLICATION_RISK",
                    "title": "JOIN 后聚合可能存在重复计算风险",
                    "severity": "medium",
                    "message": "SQL 同时存在 JOIN 和 GROUP BY，建议确认 JOIN key 是否唯一，避免一对多导致指标放大。",
                    "suggestion": "请检查 JOIN 右表是否按关联键唯一，必要时先聚合或去重。",
                    "evidence": "JOIN + GROUP BY",
                    "category": "semantic",
                    "confidence": 0.65,
                }
            )

        return {"issues": issues}

    def _generate_mock_fix_result(self, user_prompt: str) -> dict[str, Any]:
        auto_fixed_sql = self._extract_auto_fixed_sql(user_prompt)
        return {
            "fixed_sql": auto_fixed_sql,
            "applied_fixes": ["Mock LLM 已基于规则自动修复结果生成 fixed_sql。"],
            "manual_notes": [],
        }

    def _extract_auto_fixed_sql(self, user_prompt: str) -> str:
        marker = "【规则自动修复后的 SQL】"
        if marker not in user_prompt:
            return "-- MOCK_FIXED_SQL_NOT_FOUND"
        after_marker = user_prompt.split(marker, 1)[1]
        if "```sql" not in after_marker:
            return after_marker.strip()
        after_fence = after_marker.split("```sql", 1)[1]
        if "```" not in after_fence:
            return after_fence.strip()
        return after_fence.split("```", 1)[0].strip()


class DeepSeekLLMClient(BaseLLMClient):
    """DeepSeek JSON Output Client。"""

    def __init__(self) -> None:
        try:
            from dotenv import load_dotenv
            from openai import OpenAI
        except ImportError as error:
            raise LLMAPIError("请安装 openai 和 python-dotenv 依赖。") from error

        load_dotenv()

        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        if not self.api_key:
            raise LLMAPIError("未配置 DEEPSEEK_API_KEY。")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate_json(self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                # JSON Output 主要保证返回合法 JSON；字段 schema 由本地校验和 repair 保障。
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4096,
            )
        except Exception as error:
            raise LLMAPIError(str(error)) from error

        content = response.choices[0].message.content
        if not content:
            raise LLMResponseParseError("LLM 返回内容为空。")

        try:
            return json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMResponseParseError(f"LLM 返回不是合法 JSON：{content}") from error


def create_llm_client(provider: str) -> BaseLLMClient:
    provider = provider.lower()
    if provider == "mock":
        return MockLLMClient()
    if provider == "deepseek":
        return DeepSeekLLMClient()
    raise LLMAPIError(f"不支持的 LLM provider：{provider}")
