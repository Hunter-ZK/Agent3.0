
import json

from sql_pilot_engine.core.models import (
    Issue,
)


LLM_REVIEW_JSON_SCHEMA = {
    "name": "sql_review_result",
    "schema": {
        "type": "object",
        "properties": {
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rule_id": {
                            "type": "string",
                        },
                        "title": {
                            "type": "string",
                        },
                        "severity": {
                            "type": "string",
                            "enum": [
                                "low",
                                "medium",
                                "high",
                            ],
                        },
                        "message": {
                            "type": "string",
                        },
                        "suggestion": {
                            "type": "string",
                        },
                        "evidence": {
                            "type": "string",
                        },
                        "category": {
                            "type": "string",
                        },
                        "confidence": {
                            "type": "number",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "advisory",
                                "auto_fix",
                                "context_required",
                                "human_review",
                            ],
                        },
                        "auto_fixable": {
                            "type": "boolean",
                        },
                    },
                    "required": [
                        "rule_id",
                        "title",
                        "severity",
                        "message",
                        "suggestion",
                        "evidence",
                        "category",
                        "confidence",
                        "action",
                        "auto_fixable",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": [
            "issues"
        ],
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = """
你是 Agent3.0 的 SQL 智能审查器。

系统已经使用 SQLGlot、确定性 Guardrails
和 MetadataValidator 处理能够明确判断的硬事实。

你的主要职责是处理需要 SQL 理解、业务语义
和上下文推理的问题。

重点关注但不限于：

- JOIN 语义与数据放大风险
- 聚合粒度与指标口径
- NULL 处理
- 过滤条件合理性
- 日期与调度语义
- 分区使用合理性
- 数据粒度
- SQL 业务语义一致性
- 可维护性
- 性能风险

不要因为没有对应 Python Rule 就忽略问题。
也不要为了发现问题而制造问题。

action 只能是：

advisory
= 有价值的建议，但当前 SQL 仍可以可信。

auto_fix
= 当前上下文已经足够，可以安全自动修改。

context_required
= 缺少必要上下文，不能猜。

human_review
= 存在实质风险，但当前无法安全自动修复。

禁止输出 block。
BLOCK 只允许由确定性安全边界产生。

禁止编造：

- 不存在的表
- 不存在的字段
- JOIN 关系
- 指标定义
- 日期规则
- 分区值
- 业务口径

只返回符合 Schema 的 JSON object。
""".strip()


REPAIR_SYSTEM_PROMPT = """
你负责修复上一轮 SQL Review JSON。

只修复 JSON Contract，
不要重新执行 SQL Review。

最终只能返回：

{
  "issues": [
    {
      "rule_id": "LLM_EXAMPLE",
      "title": "问题标题",
      "severity": "medium",
      "message": "问题说明",
      "suggestion": "修改建议",
      "evidence": "证据",
      "category": "semantic",
      "confidence": 0.8,
      "action": "advisory",
      "auto_fixable": false
    }
  ]
}

禁止增加其他字段。
""".strip()


def build_issues_text(
    issues: list[Issue],
) -> str:

    if not issues:
        return "无确定性问题。"

    return json.dumps(
        [
            issue.to_dict()
            for issue
            in issues
        ],
        ensure_ascii=False,
        indent=2,
    )


def build_user_prompt(
    *,
    sql: str,
    file_path: str,
    guardrail_catalog_text: str,
    deterministic_issues_text: str,
    analysis_context_text: str = "",
    metadata_context_text: str = "",
) -> str:

    return f"""
请审查以下 SQL。

## 文件路径

{file_path}

## Deterministic Guardrails

{guardrail_catalog_text}

## 已发现的确定性问题

{deterministic_issues_text}

## SQL Analysis / SQLFacts

{analysis_context_text or "未提供。"}

## Metadata Context

{metadata_context_text or "未提供。"}

## SQL

```sql
{sql}
```

请基于完整上下文独立执行智能 Review，
并严格输出 JSON。
""".strip()


def build_repair_prompt(
    *,
    raw_result: dict,
    error_message: str,
    ) -> str:

    return f"""

上一轮 JSON 不符合 Contract。

Validation Error

{error_message}

Raw Result

{json.dumps(
raw_result,
ensure_ascii=False,
indent=2,
)}

请只修复 JSON 结构。
""".strip()