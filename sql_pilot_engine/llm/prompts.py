# sql_review_agent/llm/prompts.py

import json
from typing import Any

from sql_pilot_engine.core.models import Issue

LLM_REVIEW_JSON_SCHEMA = {
    "name": "sql_review_result",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rule_id": {"type": "string"},
                        "title": {"type": "string"},
                        "severity": {"type": "string"},
                        "message": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "evidence": {"type": "string"},
                        "category": {"type": "string"},
                        "confidence": {"type": "number"},
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
                },
            }
        },
        "required": ["issues"],
    },
}

SYSTEM_PROMPT = """
你是一个资深 MaxCompute / DataWorks SQL Review 助手。

你必须只输出 json，不允许输出 Markdown、解释文字、代码块或多余字段。

你输出的 json 必须严格符合以下结构：

{
  "issues": [
    {
      "rule_id": "LLM_EXAMPLE_RULE",
      "title": "问题标题",
      "severity": "medium",
      "message": "问题说明",
      "suggestion": "修改建议",
      "evidence": "SQL或上下文证据",
      "category": "semantic",
      "confidence": 0.85,
      "action": "advisory",
      "auto_fixable": false
    }
  ]
}

强制要求：
1. 根对象必须只有 issues 字段。
2. issues 必须是数组。
3. issues 中每个对象必须包含且只能包含以下 8 个字段：rule_id, title, severity, message, suggestion, evidence, category, confidence。
4. rule_id 必须以 LLM_ 开头。
5. severity 只能是 low、medium、high。
6. confidence 必须是 0 到 1 之间的数字。
7. 不允许使用 description 字段，必须使用 message 字段。
8. 不允许省略 title、message、evidence、category。
9. 如果没有补充问题，必须返回：{"issues": []}

action 必须是以下四种之一：

1. advisory
   问题值得提示，但当前 SQL 仍可被认为可信。
   例如性能、可维护性、风格、低风险优化建议。

2. auto_fix
   当前证据已经足够，可以在不猜测业务事实的情况下自动修改 SQL。

3. context_required
   无法仅凭现有 SQL / Metadata / Context 判断正确答案，需要补充业务信息。

4. human_review
   问题可能影响业务正确性，但当前无法可靠自动修复。

禁止输出 block。
真正的硬阻断由确定性 Rule / Metadata Validator 负责。

如果 action=auto_fix，则 auto_fixable 必须为 true。
其他情况通常为 false。

不要为了“发现问题”而发现问题。
只有存在明确 SQL 证据或上下文证据时才输出 Issue。

重点关注：JOIN 后聚合重复计算、聚合空值、过滤口径一致性、DataWorks 调度参数、分层设计、数据质量风险。
不要简单重复规则引擎已经明确发现的问题。
""".strip()

REPAIR_SYSTEM_PROMPT = """
你是一个 json schema 修复器。

你的任务：把上一次 LLM 返回的 json 修复为严格符合目标 schema 的 json。

目标 schema：
{
  "issues": [
    {
        "rule_id": "LLM_EXAMPLE_RULE",
        "title": "问题标题",
        "severity": "medium",
        "message": "问题说明",
        "suggestion": "修改建议",
        "evidence": "SQL 证据",
        "category": "semantic",
        "confidence": 0.7,
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
    }
  ]
}

强制要求：
1. 只输出 json。
2. 根对象必须只有 issues 字段。
3. 每个 issue 必须包含且只能包含：rule_id, title, severity, message, suggestion, evidence, category, confidence。
4. 如果原始内容中有 description，请改名为 message。
5. 如果缺少 title，请根据 rule_id 生成简短中文标题。
6. 如果缺少 evidence，请根据内容填 "LLM semantic review"。
7. 如果缺少 category，请填 "semantic"。
8. rule_id 必须以 LLM_ 开头。
9. severity 只能是 low、medium、high。
10. confidence 必须是 0 到 1 的数字。
""".strip()


def build_rule_issues_text(issues: list[Issue]) -> str:
    if not issues:
        return "规则引擎未发现明显问题。"

    lines: list[str] = []
    for index, issue in enumerate(issues, start=1):
        lines.append(f"{index}. Rule ID: {issue.rule_id}")
        lines.append(f"   Title: {issue.title}")
        lines.append(f"   Severity: {issue.severity.value}")
        lines.append(f"   Category: {issue.category}")
        lines.append(f"   Message: {issue.message}")
        lines.append(f"   Suggestion: {issue.suggestion}")
        lines.append(f"   Evidence: {issue.evidence}")
        lines.append("")
    return "\n".join(lines)


def build_user_prompt(
    sql: str,
    file_path: str,
    rule_catalog_text: str,
    rule_issues_text: str,
    analysis_context_text: str = "",
    metadata_context_text: str = "",
) -> str:
    return f"""
请审查以下 MaxCompute / DataWorks SQL，并只输出 json。

文件路径：
{file_path}

## 系统硬性规则目录
{rule_catalog_text}

## 规则引擎已发现问题
{rule_issues_text}

## SQL 结构分析上下文
{analysis_context_text or "未提供。"}

## 元数据上下文
{metadata_context_text or "未提供。"}

## SQL 原文
```sql
{sql}
```
""".strip()


def build_repair_prompt(raw_result: dict[str, Any], error_message: str) -> str:
    return f"""
上一次返回的 json 没有通过系统校验。

校验错误：
{error_message}

请把下面这个 json 修复成严格符合目标 schema 的 json。

原始 json：
{json.dumps(raw_result, ensure_ascii=False, indent=2)}
""".strip()
