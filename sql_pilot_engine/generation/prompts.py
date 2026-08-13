from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)


def render_query_context(
    context: QueryContext,
) -> str:

    sections: list[str] = []

    if context.business_knowledge:
        sections.append(
            "## Business Knowledge"
        )

        sections.extend(
            item.document.text
            for item
            in context.business_knowledge
        )

    if context.verified_sql:
        sections.append(
            "## Verified SQL Examples"
        )

        sections.extend(
            item.document.text
            for item
            in context.verified_sql
        )

    return "\n\n".join(sections)



def build_planner_prompt(
    *,
    question: str,
    semantic_context: str,
    query_context: QueryContext,
) -> str:
    
    rag_context = render_query_context(
        query_context
    )
    
    return f"""
You are a datawarehouse query planner.

User question:
{question}

Semantic model:
{semantic_context}

Retrieved context:
{rag_context}

Return JSON only.

Schema:
{{
  "tables": ["table_name"],
  "dimensions": ["column_name"],
  "metrics": ["metric_name"],
  "filters": ["condition"],
  "group_by": ["column_name"]
}}
""".strip()

def build_sql_prompt(
    *,
    question: str,
    plan: QueryPlan,
    semantic_context: str,
    query_context: QueryContext,
    dialect: str,
) -> str:
    
    rag_context = render_query_context(
        query_context
    )
    
    return f"""
Generate one SQL statement.

Dialect:
{dialect}

Question:
{question}

Query Plan:
tables={plan.tables}
dimensions={plan.dimensions}
metrics={plan.metrics}
filters={plan.filters}
group_by={plan.group_by}

Semantic model:
{semantic_context}

Retrieved context:
{rag_context}

Return SQL only.
Do not use markdown code fences.
""".strip()