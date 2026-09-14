from __future__ import annotations

import json


OPTIMIZE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "suggestions": {
            "type": "array",
            "items": {"type": "object"},
        },
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
        "suggestions": {
            "type": "array",
            "items": {"type": "object"},
        },
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
你是 Agent3.0 中的生产级 MaxCompute SQL Optimization Agent。

输入 SQL 已经通过 Trusted SQL Review。
Program / Evidence Context 是确定性结构事实的最高优先级来源。
你的职责是寻找真正有价值的优化机会，而不是重新进行安全审查。

你可以分析但不限于：
- 数据扫描范围与分区裁剪；
- 过滤下推；
- JOIN 前数据缩减；
- JOIN Key 表达式与类型转换；
- 聚合方式、DISTINCT、GROUPING SETS；
- CTE / 子查询重复计算；
- LATERAL VIEW / EXPLODE 放大；
- MAPJOIN / STREAMTABLE 等 Hint 的静态适用性；
- 不必要排序、重复表达式、投影；
- SQL 可读性与可维护性。

必须遵守：
1. 不改变业务语义；
2. 不凭空创造表或字段；
3. 不擅自改变粒度、JOIN 类型、指标口径、过滤条件；
4. 不确定语义等价时，不生成 candidate_sql；
5. 没有真实 Execution Plan / Statistics 时，不声称具体性能提升比例；
6. 依赖数据量、执行计划或运行历史的建议必须 requires_execution_validation=true；
7. candidate_sql 只是候选，后续必须通过 Program Gate、Review 和必要的执行验证。

只返回 JSON object。
""".strip()


PATCH_OPTIMIZE_SYSTEM_PROMPT = """
你是生产级 MaxCompute SQL Optimization scoped patch planner。

输入是一份超长 SQL Program。禁止 one-shot 重写整份 SQL。
Program / Evidence Context 是确定性事实的最高优先级来源。

每个 optimization patch 必须：
1. old_sql 从原 SQL 逐字复制，且在原 SQL 中唯一出现；
2. new_sql 是最小、局部、语义可证明的优化替换；
3. reason 明确说明为什么语义保持不变，以及优化依据；
4. 不得改变 write target、Statement 数、JOIN 类型、指标定义、聚合粒度和业务过滤；
5. 需要 Statistics / Execution Plan 才能确认的优化只给 suggestion，不生成 patch；
6. 无法证明语义等价时 patches 留空。

只返回 JSON object。
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
) -> str:
    payload = {
        "dialect": dialect,
        "optimization_goals": _default_goals(optimization_goals),
        "sql": sql,
        "analysis_context": analysis_context_text,
        "program_evidence_context": program_evidence_context_text,
        "metadata_context": metadata_context_text,
        "explain_context": explain_context_text,
    }

    return f"""
请根据以下 SQL Optimization Context 进行优化分析：

{json.dumps(payload, ensure_ascii=False, indent=2)}

返回 summary、suggestions、candidate_sql、rewrite_reason、assumptions、confidence。
只有能够高置信度保持语义时才返回完整 candidate_sql，否则 candidate_sql=null。
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
) -> str:
    payload = {
        "dialect": dialect,
        "optimization_goals": _default_goals(optimization_goals),
        "analysis_context": analysis_context_text,
        "program_evidence_context": program_evidence_context_text,
        "metadata_context": metadata_context_text,
        "explain_context": explain_context_text,
    }

    return f"""
这是一份超长生产 SQL Program。请先基于 Context 给出 suggestions，
只对局部、唯一、语义可证明的优化生成 scoped patches。

## Context
{json.dumps(payload, ensure_ascii=False, indent=2)}

## 原始 SQL（patch.old_sql 必须从这里逐字复制）
```sql
{sql}
```

返回 summary、suggestions、patches、rewrite_reason、assumptions、confidence。
无法证明安全的优化不要生成 patch。
""".strip()
