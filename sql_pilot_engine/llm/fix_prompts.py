# sql_review_agent/llm/fix_prompts.py

import json
from typing import Any

from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.context.query_context_renderer import (
    render_query_context,
)

FIX_JSON_SCHEMA = {
    "name": "sql_fix_result",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "fixed_sql": {"type": "string"},
            "applied_fixes": {"type": "array", "items": {"type": "string"}},
            "manual_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["fixed_sql", "applied_fixes", "manual_notes"],
    },
}

FIX_SYSTEM_PROMPT = """
你是 SQL 修复模型。

你需要综合：
- 原 SQL
- Guardrail Issues
- Metadata Issues
- LLM Review Issues
- SQLFacts
- Metadata Context
- 上一次 Critic Feedback
- Deterministic Pre-fix

生成完整 Candidate SQL。

Deterministic Pre-fix 只是参考，不是权威答案。

你可以对 SQL 做超出 Python Rule 的合理修改，
但必须有当前 Context 支撑。

禁止无依据：
- 创建表/字段
- 改 JOIN 关系
- 改指标定义
- 改聚合粒度
- 猜日期
- 猜分区值
- 猜业务口径

Context 不足时不要猜，
在 manual_notes 中说明缺什么。
""".strip()

FIX_REPAIR_SYSTEM_PROMPT = """
你是一个 json schema 修复器。

请把输入 json 修复为严格符合以下结构：
{
  "fixed_sql": "完整修复后的 SQL",
  "applied_fixes": ["修复说明1"],
  "manual_notes": ["人工确认事项1"]
}

强制要求：
1. 只输出 json。
2. 根对象必须只有 fixed_sql、applied_fixes、manual_notes。
3. fixed_sql 必须是字符串。
4. applied_fixes 必须是字符串数组。
5. manual_notes 必须是字符串数组。
""".strip()

def build_fix_user_prompt(
    *,
    original_sql: str,
    deterministic_pre_fix_sql: str,
    review_issues_text: str,
    analysis_context_text: str,
    metadata_context_text: str,
    query_context=None,
) -> str:

    return f"""
请基于完整 Review Context
生成完整 Candidate SQL。

## Query Context

{render_query_context(query_context)}

## Review Issues

{review_issues_text}

## SQL Analysis

{analysis_context_text}

## Metadata Context

{metadata_context_text}



## 原始 SQL

```sql
{original_sql}

## 确定性预修复 SQL
```sql
{deterministic_pre_fix_sql}

要求：

输出完整 fixed_sql，不要只输出修改片段。
确定性预修复 SQL 只是参考，不是权威答案。
可以执行 Python Rule 没有覆盖的合理修复。
不得无依据创造表、字段、JOIN、指标、日期、分区值和业务口径。
Context 不足时不要猜，把需要确认的内容放入 manual_notes。
""".strip()

def build_fix_repair_prompt(raw_result: dict[str, Any], error_message: str) -> str:
    return f"""
上一次返回的 json 没有通过系统校验。

校验错误：
{error_message}

请修复下面这个 json，使其严格符合 fixed_sql schema。

原始 json：
{json.dumps(raw_result, ensure_ascii=False, indent=2)}
""".strip()
