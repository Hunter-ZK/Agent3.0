# sql_review_agent/llm/clients.py
from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
)

from sql_pilot_engine.llm.transport import (
    OpenAICompatibleTransport,
)

from sql_pilot_engine.llm.errors import LLMAPIError, LLMResponseParseError

from sql_pilot_engine.config.llm import LLMRequestConfig

import json
from typing import Any


class MockLLMClient():
    """用于测试和离线开发的 Mock LLM。"""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:

        _ = system_prompt

        schema = json_schema.get(
            "schema",
            json_schema,
        )

        required = set(
            schema.get(
                "required",
                [],
            )
        )

        if {
            "fixed_sql",
            "applied_fixes",
            "manual_notes",
        } <= required:
            return (
                self._generate_mock_fix_result(
                    user_prompt
                )
            )

        if {
            "summary",
            "suggestions",
            "candidate_sql",
            "rewrite_reason",
            "assumptions",
            "confidence",
        } <= required:
            return (
                self
                ._generate_mock_optimize_result()
            )

        if {
            "sql_summary",
            "main_tables",
            "output_columns",
        } <= required:
            return (
                self
                ._generate_mock_explain_result()
            )
            
        if {
            "status",
            "missing_requirements",
            "issues",
        } <= required:

            return {
                "status": "pass",

                "missing_requirements": [],

                "issues": [],
            }

        return (
            self._generate_mock_review_result(
                user_prompt
            )
        )

    @staticmethod
    def _generate_mock_explain_result(
    ) -> dict[str, Any]:

        return {
            "sql_summary": (
                "Mock SQL explain result."
            ),
            "business_purpose": None,
            "main_tables": [],
            "output_columns": [],
            "cte_steps": [],
            "cte_dependencies": [],
            "suspicious_points": [],
            "uncertainties": [],
            "route_signals": {
                "need_metadata": False,
                "need_rag": False,
                "need_review": True,
                "need_human_confirm": False,
                "can_auto_fix": False,
                "next_node": "review",
            },
        }

    @staticmethod
    def _generate_mock_optimize_result(
    ) -> dict[str, Any]:

        return {
            "summary": (
                "Mock optimizer 未发现需要"
                "自动改写的优化机会。"
            ),
            "suggestions": [],
            "candidate_sql": None,
            "rewrite_reason": None,
            "assumptions": [],
            "confidence": 1.0,
        }

    @staticmethod
    def _generate_mock_review_result(
        user_prompt: str,
    ) -> dict[str, Any]:

        issues: list[
            dict[str, Any]
        ] = []

        lower_prompt = (
            user_prompt.lower()
        )

        if (
            "sum(" in lower_prompt
            and "coalesce"
            not in lower_prompt
            and "nvl"
            not in lower_prompt
        ):
            issues.append(
                {
                    "rule_id": (
                        "LLM_AGGREGATION_"
                        "NULL_HANDLING_SUGGESTION"
                    ),
                    "title": (
                        "聚合金额字段建议"
                        "考虑空值处理"
                    ),
                    "severity": "medium",
                    "message": (
                        "检测到聚合计算中可能未"
                        "显式处理空值。"
                    ),
                    "suggestion": (
                        "如字段可能为空，可考虑"
                        "使用 COALESCE 或 NVL。"
                    ),
                    "evidence": (
                        "sum(...) has no "
                        "null handling"
                    ),
                    "category": "semantic",
                    "confidence": 0.7,
                    "action": "advisory",
                    "auto_fixable": False,
                }
            )

        if (
            " join " in lower_prompt
            and " group by "
            in lower_prompt
        ):
            issues.append(
                {
                    "rule_id": (
                        "LLM_JOIN_DUPLICATION_RISK"
                    ),
                    "title": (
                        "JOIN 后聚合可能存在"
                        "重复计算风险"
                    ),
                    "severity": "medium",
                    "message": (
                        "SQL 同时存在 JOIN 和 "
                        "GROUP BY，需要确认 "
                        "JOIN key 是否唯一。"
                    ),
                    "suggestion": (
                        "检查右表关联键唯一性，"
                        "必要时先聚合或去重。"
                    ),
                    "evidence": (
                        "JOIN + GROUP BY"
                    ),
                    "category": "semantic",
                    "confidence": 0.65,
                    "action": "advisory",
                    "auto_fixable": False,
                }
            )

        return {
            "issues": issues
        }

    def _generate_mock_fix_result(
        self,
        user_prompt: str,
    ) -> dict[str, Any]:

        auto_fixed_sql = (
            self._extract_auto_fixed_sql(
                user_prompt
            )
        )

        return {
            "fixed_sql": auto_fixed_sql,
            "applied_fixes": [
                (
                    "Mock LLM 基于规则、SQL 分析"
                    "和上下文生成 fixed_sql。"
                )
            ],
            "manual_notes": [],
        }

    @staticmethod
    def _extract_auto_fixed_sql(
        user_prompt: str,
    ) -> str:

        marker = (
            "## 确定性预修复 SQL"
        )

        if marker not in user_prompt:
            return (
                "-- MOCK_FIXED_SQL_NOT_FOUND"
            )

        after_marker = (
            user_prompt
            .split(
                marker,
                1,
            )[1]
        )

        if "```sql" not in after_marker:
            return after_marker.strip()

        after_fence = (
            after_marker
            .split(
                "```sql",
                1,
            )[1]
        )

        if "```" not in after_fence:
            return after_fence.strip()

        return (
            after_fence
            .split(
                "```",
                1,
            )[0]
            .strip()
        )


class DeepSeekLLMClient():
    """DeepSeek JSON Output Client。"""

    def __init__(
        self,
        *,
        transport: OpenAICompatibleTransport,
        request_config: LLMRequestConfig,
    ) -> None:

        self._transport = transport
        
        self._request_config = request_config

    @staticmethod
    def _build_structured_system_prompt(
        *,
        system_prompt: str,
        json_schema: dict[str, Any],
    ) -> str:
        """将本次调用的 JSON Schema 转成模型可理解的输出约束。

        注意：
        - 不知道调用方是 Reviewer / Fixer / Explainer；
        - 不包含任何 SQL Review 专属字段；
        - Schema 完全由调用方传入。
        """

        schema = json_schema.get(
            "schema",
            json_schema,
        )

        schema_text = json.dumps(
            schema,
            ensure_ascii=False,
            indent=2,
        )

        return f"""
    {system_prompt}

    ## Structured JSON Output Contract

    本次任务要求返回结构化 JSON。

    你必须严格按照以下 JSON Schema 输出：

    {schema_text}

    要求：

    - 只返回 JSON object；
    - 不返回 Markdown code fence；
    - 不返回 JSON 之外的解释文字；
    - 不修改字段名；
    - 不遗漏 required 字段；
    - 不增加 Schema 未允许的字段；
    - number、boolean、string、array、object 等字段类型必须严格匹配 Schema；
    - 字段层级必须严格匹配 Schema。
    """.strip()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:

        structured_system_prompt = (
            self._build_structured_system_prompt(
                system_prompt=system_prompt,
                json_schema=json_schema,
            )
        )

        try:
            content = (
                self._transport.complete(
                    messages=(
                        {
                            "role":"system",
                            "content":(
                                structured_system_prompt
                            ),
                        },
                        {
                            "role": "user",
                            "content":(
                                user_prompt
                            ),
                        },
                    ),
                
                    request_config = self._request_config,
                    
                    response_format = {
                        "type": "json_object",
                    },
                )
            )
        except Exception as error:
            raise LLMAPIError(str(error)) from error

        if not content:
            raise LLMResponseParseError("LLM 返回内容为空。")

        try:
            return json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMResponseParseError(f"LLM 返回不是合法 JSON：{content}") from error


def create_llm_client(provider: str) -> StructuredGenerationModel:
    provider = provider.lower()
    if provider == "mock":
        return MockLLMClient()
    if provider == "deepseek":
        return DeepSeekLLMClient()
    raise LLMAPIError(f"不支持的 LLM provider：{provider}")
