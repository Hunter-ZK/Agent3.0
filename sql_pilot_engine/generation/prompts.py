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
  "requirements",["requirements"]
}}

Planning rules:

- Preserve every material requirement from the original question.
- Use tables, dimensions, metrics, filters and group_by
  for requirements that fit those structures.
- Put requirements that cannot be fully represented by those
  fields into "requirements".
- Do not silently omit requirements such as time comparison,
  ranking, Top N, ratio, trend or other analytical operations.
- Do not invent requirements that are not present in the question
  or context.
""".strip()

def build_sql_prompt(
    *,
    question: str,
    plan: QueryPlan,
    semantic_context: str,
    query_context: QueryContext,
    dialect: str,
    revision_feedback: tuple[str, ...] = (),
) -> str:
    
    rag_context = render_query_context(
        query_context
    )
    
    feedback_text = ""
    
    if revision_feedback:
        feedback_lines = "\n".join(
            f"- {item}"
            for item in revision_feedback
        )

        feedback_text = f"""
        Previous SQL was rejected.

        Revision feedback:
        {feedback_lines}

        Generate a revised SQL that addresses every
        feedback item while still satisfying the
        original user question and business context.
        """.strip()

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
requirements={plan.requirements}

Semantic model:
{semantic_context}

Retrieved context:
{rag_context}

Retrieved context:
{render_query_context(query_context)}

{feedback_text}

Generate SQL only.
""".strip()