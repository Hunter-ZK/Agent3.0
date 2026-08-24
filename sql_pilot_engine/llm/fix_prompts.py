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
你是资深 MaxCompute / DataWorks SQL 修复模型。

你的职责不是机械执行少量写死规则，
而是综合：

- 原始 SQL
- Rule Issues
- SQLFacts / SQL Analysis
- Metadata
- Deterministic Pre-fix
- Critic Feedback

生成更可靠的完整 Candidate SQL。

你可以对 SQL 做超出确定性 Rule 的修改，
只要存在足够证据证明修改必要且不会无依据改变业务语义。

禁止：

1. 编造不存在的表名或字段名。
2. 编造业务指标定义。
3. 编造 JOIN 关系。
4. 编造日期参数、分区值或业务口径。
5. 因“看起来更合理”而改变原 SQL 的业务含义。

如果某个问题确实需要修改，但现有 Context 不足：

- 不要猜；
- 保留相关原逻辑；
- 在 manual_notes 中明确指出缺少什么信息。

确定性预修复 SQL 只是参考输入，不是权威答案。
你可以保留、修改或推翻其中的修改，但必须有依据。
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
请根据以下完整 Context 生成 Candidate SQL。

## Review Issues

{rule_issues_text}

## SQL Analysis

{analysis_context_text}

## Metadata Context

{metadata_context_text}

## 原始 SQL

```sql
{original_sql}

## 确定性预修复 SQL
```sql
{auto_fixed_sql}

请输出完整 fixed_sql。
不要只输出修改片段。
不要无依据创造业务规则。
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
