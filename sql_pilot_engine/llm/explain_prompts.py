EXPLAIN_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "sql_summary": {
            "type": "string",
        },
        "business_purpose": {},
        "main_tables": {
            "type": "array",
        },
        "output_columns": {
            "type": "array",
        },
        "cte_steps": {
            "type": "array",
        },
        "cte_dependencies": {
            "type": "array",
        },
        "suspicious_points": {
            "type": "array",
        },
        "uncertainties": {
            "type": "array",
        },
        "route_signals": {
            "type": "object",
        },
    },
    "required": [
        "sql_summary",
        "main_tables",
        "output_columns",
    ],
}


EXPLAIN_SYSTEM_PROMPT = """
你是 MaxCompute SQL Explain 模型。

请解释 SQL 的结构和业务含义，
为后续 Review、Metadata、Optimization
提供结构化上下文。

只能返回 JSON object。
""".strip()


def build_explain_user_prompt(
    sql: str,
) -> str:
    return f"""
请分析以下 SQL：

```sql
{sql}
```
返回：

* sql_summary
* business_purpose
* main_tables
* output_columns
* cte_steps
* cte_dependencies
* suspicious_points
* uncertainties
* route_signals
""".strip()