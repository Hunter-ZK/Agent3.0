from __future__ import annotations

import json


OPTIMIZE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
        },
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
            },
        },
        "candidate_sql": {
            "type": [
                "string",
                "null",
            ],
        },
        "rewrite_reason": {
            "type": [
                "string",
                "null",
            ],
        },
        "assumptions": {
            "type": "array",
        },
        "confidence": {
            "type": "number",
        },
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


OPTIMIZE_SYSTEM_PROMPT = """
你是 Agent3.0 中的 MaxCompute SQL Optimization Agent。

输入 SQL 已经通过 Trusted SQL Review。
你的职责是主动寻找真正有价值的 SQL 优化机会，
而不是重新进行 SQL 安全审查。

你可以分析但不限于：

- 数据扫描范围；
- 分区裁剪；
- 过滤条件位置；
- JOIN 前的数据缩减；
- JOIN Key 表达式与类型转换；
- 聚合方式；
- DISTINCT；
- CTE / 子查询重复计算；
- 不必要的排序；
- 重复表达式；
- SELECT 投影；
- SQL 可读性与可维护性；
- MaxCompute 常见性能问题。

以上不是固定规则列表。
如果存在其他合理优化方式，可以主动提出。

必须遵守：

1. 不改变业务语义。
2. 不凭空创造表或字段。
3. 不擅自改变查询粒度。
4. 不擅自删除业务过滤条件。
5. 不擅自修改 JOIN 类型。
6. 不擅自修改指标计算口径。
7. 不确定语义等价时，不生成 candidate_sql。
8. 没有真实 Execution Plan / Stats 时，
   不声称具体性能提升比例。
9. 如果建议依赖真实数据量、执行计划或运行历史，
   必须明确标记 requires_execution_validation。
10. candidate_sql 只是候选方案，
    后续还会进行 Review 与语义验证。

只返回 JSON object。
不要返回 Markdown。
""".strip()


def build_optimize_user_prompt(
    *,
    sql: str,
    dialect: str,
    optimization_goals: list[str],
    analysis_context_text: str,
    metadata_context_text: str,
    explain_context_text: str,
) -> str:

    payload = {
        "dialect": dialect,
        "optimization_goals": (
            optimization_goals
            or [
                (
                    "保持业务语义完全不变，"
                    "优化性能、资源消耗和可维护性。"
                )
            ]
        ),
        "sql": sql,
        "analysis_context": (
            analysis_context_text
        ),
        "metadata_context": (
            metadata_context_text
        ),
        "explain_context": (
            explain_context_text
        ),
    }

    return f"""
请根据以下 SQL Optimization Context 进行优化分析：

{json.dumps(
    payload,
    ensure_ascii=False,
    indent=2,
)}

返回：

{{
  "summary": "总体优化分析",
  "suggestions": [
    {{
      "category": "优化类别",
      "priority": "low|medium|high",
      "description": "优化建议",
      "reason": "判断依据",
      "expected_benefit": "预期收益，不得编造性能数字",
      "risk": "潜在语义或执行风险",
      "requires_execution_validation": false
    }}
  ],
  "candidate_sql": "能够高置信度保持语义时返回完整SQL，否则null",
  "rewrite_reason": "为什么这样改，没有candidate时为null",
  "assumptions": [],
  "confidence": 0.0
}}
""".strip()