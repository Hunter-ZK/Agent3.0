# sql_review_agent/llm/fix_prompts.py

import json
from typing import Any

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
你是一个资深 MaxCompute / DataWorks SQL 修复助手。

你必须只输出 json，不允许输出 Markdown、解释文字、代码块或多余字段。

你输出的 json 必须严格符合以下结构：
{
  "fixed_sql": "完整修复后的 SQL",
  "applied_fixes": ["修复说明1"],
  "manual_notes": ["人工确认事项1"]
}

强制要求：
1. 根对象必须只有 fixed_sql、applied_fixes、manual_notes 三个字段。
2. fixed_sql 必须是一份完整 SQL，不允许只输出片段。
3. 不要删除原 SQL 的业务逻辑。
4. 对明确语法问题可以直接修复。
5. 对字段名、表名、业务口径不确定的问题，不要强行改名。
6. 不确定的问题必须以 SQL 注释形式保留：-- AI_REVIEW_TODO: ...
7. applied_fixes 记录已经明确应用的修改。
8. manual_notes 记录需要人工确认的事项。
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
    original_sql: str,
    auto_fixed_sql: str,
    rule_issues_text: str,
    analysis_context_text: str,
    metadata_context_text: str,
) -> str:
    return f"""
请基于以下材料生成完整 fixed SQL。

【规则已发现问题】
{rule_issues_text}

【SQL 结构分析上下文】
{analysis_context_text}

【元数据上下文】
{metadata_context_text}

【原始 SQL】
```sql
{original_sql}
```

【规则自动修复后的 SQL】
```sql
{auto_fixed_sql}
```
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
