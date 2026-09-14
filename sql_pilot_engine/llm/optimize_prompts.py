from __future__ import annotations

import json


OPTIMIZE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "suggestions": {"type": "array", "items": {"type": "object"}},
        "candidate_sql": {"type": ["string", "null"]},
        "rewrite_reason": {"type": ["string", "null"]},
        "assumptions": {"type": "array"},
        "confidence": {"type": "number"},
    },
    "required": [
        "summary",
        "suggestions",
        "candidate_sql",
        "rewrite_reason",
        "assumptions",
        "confidence",
    ],
}


PATCH_OPTIMIZE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "suggestions": {"type": "array", "items": {"type": "object"}},
        "patches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "old_sql": {"type": "string"},
                    "new_sql": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["old_sql", "new_sql", "reason"],
            },
        },
        "rewrite_reason": {"type": ["string", "null"]},
        "assumptions": {"type": "array"},
        "confidence": {"type": "number"},
    },
    "required": [
        "summary",
        "suggestions",
        "patches",
        "rewrite_reason",
        "assumptions",
        "confidence",
    ],
}


OPTIMIZE_SYSTEM_PROMPT = """
你是 Agent3.0 中的生产级 MaxCompute SQL Optimization Rewriter。

前置 Optimization Advisor 已识别优化机会。你只允许基于提供的 rewrite-safe opportunities 生成候选改写。
Program / Evidence Context 是确定性结构事实的最高优先级来源。

必须遵守：
1. 不改变业务语义；
2. 不凭空创造表或字段；
3. 不擅自改变粒度、JOIN 类型、指标口径、过滤条件；
4. 不确定语义等价时，不生成 candidate_sql；
5. 没有 Execution Plan / Statistics 时，不声称具体性能提升比例；
6. requires_statistics=true 的机会不能形成候选；
7. candidate_sql 仍必须通过 Program Gate、Review 和必要的执行验证；
8. 只返回 JSON object。
""".strip()


PATCH_OPTIMIZE_SYSTEM_PROMPT = """
你是生产级 MaxCompute SQL Optimization scoped patch rewriter。

输入是一份超长 SQL Program。禁止 one-shot 重写整份 SQL。
你只能针对前置 Advisor 标记为 rewrite_safe=true 的机会生成 patch。

每个 optimization patch 必须：
1. old_sql 从原 SQL 逐字复制，且在原 SQL 中唯一出现；
2. new_sql 是最小、局部、语义可证明的优化替换；
3. reason 对应一个 rewrite-safe opportunity，并说明语义保持依据；
4. 不得改变 write target、Statement 数、JOIN 类型、指标定义、聚合粒度和业务过滤；
5. 需要 Statistics / Execution Plan 才能确认的优化只保留 suggestion，不生成 patch；
6. 无法证明语义等价时 patches 留空；
7. 只返回 JSON object。
""".strip()


def _default_goals(optimization_goals: list[str]) -> list[str]:
    return optimization_goals or [
        "保持业务语义完全不变，优化性能、资源消耗和可维护性。"
    ]


def build_optimize_user_prompt(
    *,
    sql: str,
    dialect: str,
    optimization_goals: list[str],
    analysis_context_text: str,
    metadata_context_text: str,
    explain_context_text: str,
    program_evidence_context_text: str = "",
    opportunities_text: str = "",
) -> str:
    payload = {
        "dialect": dialect,
        "optimization_goals": _default_goals(optimization_goals),
        "rewrite_safe_opportunities": opportunities_text,
        "sql": sql,
        "analysis_context": analysis_context_text,
        "program_evidence_context": program_evidence_context_text,
        "metadata_context": metadata_context_text,
        "explain_context": explain_context_text,
    }
    return f"""
请根据以下已经过 Advisor 筛选的 SQL Optimization Context 生成候选：

{json.dumps(payload, ensure_ascii=False, indent=2)}

返回 summary、suggestions、candidate_sql、rewrite_reason、assumptions、confidence。
只有能够高置信度保持语义且有 rewrite-safe opportunity 时才返回 candidate_sql，否则 candidate_sql=null。
""".strip()


def build_patch_optimize_user_prompt(
    *,
    sql: str,
    dialect: str,
    optimization_goals: list[str],
    analysis_context_text: str,
    metadata_context_text: str,
    explain_context_text: str,
    program_evidence_context_text: str,
    opportunities_text: str = "",
) -> str:
    payload = {
        "dialect": dialect,
        "optimization_goals": _default_goals(optimization_goals),
        "rewrite_safe_opportunities": opportunities_text,
        "analysis_context": analysis_context_text,
        "program_evidence_context": program_evidence_context_text,
        "metadata_context": metadata_context_text,
        "explain_context": explain_context_text,
    }
    return f"""
这是一份超长生产 SQL Program。只对 Advisor 已确认 rewrite_safe 的机会生成 scoped patches。

## Context
{json.dumps(payload, ensure_ascii=False, indent=2)}

## 原始 SQL（patch.old_sql 必须从这里逐字复制）
```sql
{sql}
```

返回 summary、suggestions、patches、rewrite_reason、assumptions、confidence。
无法证明安全的优化不要生成 patch。
""".strip()
