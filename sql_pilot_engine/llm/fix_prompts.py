import json
from typing import Any

from sql_pilot_engine.context.query_context_renderer import render_query_context


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


PATCH_FIX_JSON_SCHEMA = {
    "name": "sql_patch_fix_result",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "patches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "old_sql": {"type": "string"},
                        "new_sql": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["old_sql", "new_sql", "reason"],
                },
            },
            "manual_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["patches", "manual_notes"],
    },
}


FIX_SYSTEM_PROMPT = """
你是生产 SQL 修复模型。

Fix Diagnosis 已经先分析 Review Issue 的根因和证据边界。你只能在 Review / Diagnosis /
Program Evidence 支持的范围内生成 Candidate。

Program / Evidence Context 中的 statement、physical table、write target、lineage、hint 是确定性事实，
不得被模型自行推翻。

禁止无依据：
- 创建表/字段
- 改 JOIN 关系
- 改指标定义
- 改聚合粒度
- 猜日期
- 猜分区值
- 猜业务口径

Diagnosis 为 insufficient_context 或 required_context 非空时，不要猜修复；放入 manual_notes。
Candidate 仍必须 Re-review / Critic，不能因为由模型生成就直接可信。
""".strip()


PATCH_FIX_SYSTEM_PROMPT = """
你是生产级 SQL scoped patch planner。

目标不是重写整份 SQL，而是在超长 SQL Program 中，根据已经完成的 Fix Diagnosis 提出最小、可验证的源码替换。

每个 patch 必须：
1. old_sql 是原 SQL 中真实存在、连续、唯一出现的源码片段；
2. new_sql 只做解决当前 confirmed Diagnosis 所必需的最小修改；
3. reason 明确对应 Review Issue / Diagnosis；
4. 不得无依据改变物理表、写入目标、JOIN 关系、指标定义、聚合粒度、日期、分区或业务口径；
5. Diagnosis 不是 confirmed、auto_fix_safe=false、required_context 非空，或无法安全定位时，不生成 patch，写入 manual_notes；
6. 不返回完整 SQL，只返回 patches + manual_notes。

Program / Evidence Context 是确定性事实的最高优先级来源。
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
    diagnosis_text: str,
    analysis_context_text: str,
    metadata_context_text: str,
    program_evidence_context_text: str = "",
    query_context=None,
) -> str:
    return f"""
请基于完整 Review + Diagnosis Context 生成 Candidate SQL。

## Query Context
{render_query_context(query_context)}

## Review Issues
{review_issues_text}

## Fix Diagnosis
{diagnosis_text}

## SQL Analysis
{analysis_context_text}

## Production Program / Evidence Context
{program_evidence_context_text or '无可用 Program/Evidence Context。'}

## Metadata Context
{metadata_context_text}

## 原始 SQL
```sql
{original_sql}
```

## 确定性预修复 SQL
```sql
{deterministic_pre_fix_sql}
```

要求：
- 输出完整 fixed_sql；
- 只修 Diagnosis 有证据支持的问题；
- insufficient_context / required_context 非空的项不要猜；
- 不得无依据创造表、字段、JOIN、指标、日期、分区值和业务口径；
- 无法安全修的内容写入 manual_notes。
""".strip()


def build_patch_fix_user_prompt(
    *,
    original_sql: str,
    deterministic_pre_fix_sql: str,
    review_issues_text: str,
    diagnosis_text: str,
    analysis_context_text: str,
    metadata_context_text: str,
    program_evidence_context_text: str,
    query_context=None,
) -> str:
    return f"""
这是一份超长生产 SQL Program。禁止 one-shot 重写整份 SQL。
请只生成可由系统精确应用的 scoped patches。

## Query Context
{render_query_context(query_context)}

## Review Issues
{review_issues_text}

## Fix Diagnosis
{diagnosis_text}

## SQL Analysis
{analysis_context_text}

## Production Program / Evidence Context
{program_evidence_context_text}

## Metadata Context
{metadata_context_text}

## Deterministic Pre-fix
```sql
{deterministic_pre_fix_sql}
```

## 原始 SQL（patch.old_sql 必须从这里逐字复制）
```sql
{original_sql}
```

只返回 patches + manual_notes。
只有 confirmed、auto_fix_safe=true、required_context 为空的 Diagnosis 才允许形成 patch；否则必须留给人工确认。
""".strip()


def build_fix_repair_prompt(
    raw_result: dict[str, Any],
    error_message: str,
) -> str:
    return f"""
上一次返回的 json 没有通过系统校验。

校验错误：
{error_message}

请修复下面这个 json，使其严格符合 fixed_sql schema。

原始 json：
{json.dumps(raw_result, ensure_ascii=False, indent=2)}
""".strip()
