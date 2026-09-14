EXPLAIN_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "sql_summary": {"type": "string"},
        "business_purpose": {},
        "main_tables": {"type": "array"},
        "output_columns": {"type": "array"},
        "cte_steps": {"type": "array"},
        "cte_dependencies": {"type": "array"},
        "suspicious_points": {"type": "array"},
        "uncertainties": {"type": "array"},
        "route_signals": {"type": "object"},
    },
    "required": [
        "sql_summary",
        "main_tables",
        "output_columns",
    ],
}


EXPLAIN_SYSTEM_PROMPT = """
你是生产级 MaxCompute / DataWorks SQL Explain 模型。

输入包含两部分：
1. Agent3 确定性 Program/Evidence Context；
2. 受控长度的 SQL excerpt。

规则：
- Program/Evidence Context 是结构事实的最高优先级来源；
- 不得自行改写或推翻 statement、CTE dependency、physical table、write target、lineage、hint 等确定性事实；
- Metadata / Lineage 缺失时必须明确标记 uncertainty，不得猜测；
- SQL excerpt 可能被截断，不能把未看到的 SQL 片段当作不存在；
- business_purpose 可以基于表名、字段名、表达式和上下文做保守推断，但推断必须与 uncertainty 区分；
- suspicious_points 只描述值得 Review 的事实或风险，不直接生成自动修复结论；
- 只能返回 JSON object。
""".strip()


def _sql_excerpt(
    sql: str,
    *,
    limit: int = 12000,
) -> str:
    normalized = sql.strip()
    if len(normalized) <= limit:
        return normalized

    half = limit // 2
    return (
        normalized[:half]
        + "\n\n-- [SQL EXCERPT TRUNCATED: middle omitted] --\n\n"
        + normalized[-half:]
    )


def build_explain_user_prompt(
    sql: str,
    *,
    evidence_context: str,
) -> str:
    return f"""
## Deterministic Program / Evidence Context

```json
{evidence_context}
```

## SQL excerpt

```sql
{_sql_excerpt(sql)}
```

请在不覆盖确定性 Evidence 的前提下补充：
- sql_summary：面向工程人员的整体作用说明；
- business_purpose：可以确认或保守推断的业务目的；
- suspicious_points：需要 Review 的结构/语义关注点；
- uncertainties：Metadata、Lineage、业务语义等无法确认的内容；
- route_signals：后续是否需要 Metadata / Review / Human confirm。

main_tables、output_columns、cte_steps、cte_dependencies 可以返回，但它们只作为语言增强；
最终系统会以确定性 Program/Evidence Context 为准。
""".strip()
