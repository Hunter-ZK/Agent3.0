from __future__ import annotations

from sql_pilot_engine.context.builder import QueryContext
from sql_pilot_engine.context.query_context_renderer import render_query_context
from sql_pilot_engine.generation.models import QueryPlan
from sql_pilot_engine.linking.models import LinkedSchema


def render_linked_schema(
    linked_schema: LinkedSchema,
) -> str:
    """Render only the physical facts that the generator is allowed to use."""

    lines: list[str] = []

    if linked_schema.bindings:
        lines.append("Resolved bindings:")
        for binding in linked_schema.bindings:
            target = binding.physical_table
            if binding.physical_columns:
                target += "." + ", ".join(binding.physical_columns)
            lines.append(
                f"- {binding.kind.value}: "
                f"{binding.logical_name} -> {target}"
            )
        lines.append("")

    for linked_table in linked_schema.tables:
        table = linked_table.metadata
        lines.append(f"TABLE {table.full_name}")

        description = table.business.description
        if description:
            lines.append(f"Description: {description}")

        partition_fields = table.technical.partition_fields
        if partition_fields:
            lines.append(
                "Partition fields: "
                + ", ".join(partition_fields)
            )

        lines.append("Columns:")
        for column in table.columns.values():
            line = f"- {column.name}"

            data_type = column.technical.data_type
            if data_type:
                line += f" [{data_type}]"

            column_description = column.business.description
            if column_description:
                line += f": {column_description}"

            lines.append(line)

        lines.append("")

    if linked_schema.omitted_column_count > 0:
        lines.append(
            "OMITTED PHYSICAL COLUMNS: "
            f"{linked_schema.omitted_column_count}"
        )

    return "\n".join(lines).strip()


def build_planner_prompt(
    *,
    query_context: QueryContext,
) -> str:
    """Build the planner prompt around sufficiency, ambiguity, and explicit user constraints."""

    context_text = render_query_context(query_context)

    return f"""
You are a data warehouse query planner.

Your job is to decide whether the supplied context is sufficient to form a reliable QueryPlan.
Do not generate SQL.

Task Context:
{context_text}

Planning rules:
- The original User Question has highest priority for task-specific constraints.
- Preserve explicit dates, periods, organizations, regions, categories, filters, dimensions and requested metrics.
- Explicit user values override default conventions from Semantic Model, Retrieved Context, Verified SQL or Session Context.
- Runtime defaults such as '${{p_month_yyyymm}}' apply only when the user did not give the corresponding value.
- Treat Session Context as information explicitly supplied by the user for this task.
- Use one clear Semantic Model mapping directly; do not ask the user to confirm internal field names.
- Do not invent business definitions, tables, columns, metrics, filters, parameters or date conventions.
- Verified SQL examples are implementation references, not evidence that an ambiguous question belongs to the example's business subject.
- QueryPlan.filters must contain every already-resolved task constraint that materially changes the result.
- Ask for clarification only when missing or ambiguous information leaves two or more materially different interpretations.
- Never repeat a clarification that Session Context already answers.
- Prefer one concise clarification question that groups related missing information.

Return JSON only.

When sufficient:
{{
  "status": "ready",
  "plan": {{
    "tables": ["logical_table_name"],
    "dimensions": ["logical_dimension_name"],
    "metrics": ["metric_name"],
    "filters": ["condition"],
    "group_by": ["logical_dimension_name"],
    "requirements": ["other material requirement"]
  }}
}}

When insufficient:
{{
  "status": "need_clarification",
  "clarification_question": "one concise question",
  "missing_context": ["missing information"],
  "reason": "why it is required"
}}
""".strip()


def build_sql_prompt(
    *,
    plan: QueryPlan,
    linked_schema: LinkedSchema,
    query_context: QueryContext,
    dialect: str,
    revision_feedback: tuple[str, ...] = (),
) -> str:
    """Build the fallback/retry SQL generation prompt from resolved physical schema."""

    physical_schema = render_linked_schema(linked_schema)
    context_text = render_query_context(query_context)

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

Generate a revised SQL that addresses every feedback item while preserving the original task.
""".strip()

    return f"""
Generate exactly one SQL statement.

Dialect:
{dialect}

Task Context:
{context_text}

Query Plan:
tables={plan.tables}
dimensions={plan.dimensions}
metrics={plan.metrics}
filters={plan.filters}
group_by={plan.group_by}
requirements={plan.requirements}

Physical schema for this task:
{physical_schema}

Rules:
- Use only physical tables and columns present in LinkedSchema.
- Do not invent replacement tables or columns.
- Semantic Model / Task Context defines business meaning; LinkedSchema defines available physical objects.
- Prefer fully qualified physical table names from LinkedSchema.
- Preserve every material filter and grouping requirement from QueryPlan.
- If revision feedback is present, address all of it without dropping original requirements.
- Return SQL only. Do not wrap it in explanation text.

{feedback_text}
""".strip()
