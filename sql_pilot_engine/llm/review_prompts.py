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
你是 SQL Review 的主要智能审查器。

Deterministic Guardrails 与 MetadataValidator
已经负责能够确定判断的硬事实。

你的职责是处理需要 SQL 理解和上下文推理的问题，包括但不限于：

- JOIN 语义与重复放大风险
- 聚合口径
- NULL 处理
- 过滤逻辑
- 日期和调度语义
- 分区使用合理性
- 数据粒度
- 业务语义一致性
- SQL 可维护性
- 潜在性能问题

不要因为没有对应的 Python Rule 就忽略问题。
也不要为了发现问题而强行制造问题。

action：

advisory
= 有建议，但 SQL 仍可信。

auto_fix
= 当前信息充分，可以自动修改。

context_required
= 缺少业务或环境信息，不能猜。

human_review
= 有实质性风险，但不能安全自动处理。

禁止输出 block。
BLOCK 由 Deterministic Guardrails 决定。

禁止编造：
- 表
- 字段
- JOIN 关系
- 指标口径
- 日期规则
- 分区值
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
