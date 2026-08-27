from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
)

from sql_pilot_engine.context.query_context_renderer import (
    render_query_context,
)


def render_linked_schema(
    linked_schema: LinkedSchema,
) -> str:
    
    
    
    lines: list[str] = []


    if linked_schema.bindings:

        lines.append(
            "Resolved bindings:"
        )

        for binding in (
            linked_schema.bindings
        ):

            target = (
                binding.physical_table
            )

            if binding.physical_columns:

                target += (
                    "."
                    + ", ".join(
                        binding
                        .physical_columns
                    )
                )

            lines.append(
                "- "
                f"{binding.kind.value}: "
                f"{binding.logical_name} "
                f"-> {target}"
            )

        lines.append("")

    for linked_table in (
        linked_schema.tables
    ):
        table = (
            linked_table.metadata
        )
        
        lines.append(
            f"TABLE {table.full_name}"
        )
        
        if table.description:
            lines.append(
                "Description: "
                f"{table.description}"
            )

        if table.partition_fields:
            lines.append(
                "Partition fields: "
                + ", ".join(
                    table.partition_fields
                )
            )
            
        lines.append(
            "Columns:"
        )
        
        for column in table.columns.values():
            line = (
                f"- {column.name}"
            )
            
            if column.data_type:
                line += (
                    f" [{column.data_type}]"
                )
            
            if column.description:
                line += (
                    f": {column.description}"
                )
            
            lines.append(line)
            
    if linked_schema.omitted_column_count > 0:
        lines.append(
            "OMITTED PHYSICAL COLUMNS: "
            f"{linked_schema.omitted_column_count}"
        )

    return "\n".join(lines)


def build_planner_prompt(
    *,
    query_context: QueryContext,
) -> str:
  
    
    context_text = render_query_context(
        query_context
    )
    
    return f"""
You are a datawarehouse query planner.

Your first responsibility is to determine whether
the supplied context is sufficient to plan a
reliable SQL query.

Task Context:

{context_text}

Rules:

- Use the Semantic Model, Retrieved Context and
  Session Context together.

- Do not invent business definitions, table mappings,
  runtime parameters, date conventions or other
  required business knowledge.

- Do not ask the user for information that can already
  be reliably derived from the supplied context.

- If required information is missing or ambiguous,
  ask one concise clarification question.

- Only return "ready" when there is enough information
  to produce a reliable query plan.
  
- Session Context contains information supplied by the user
  during the current task. Treat it as valid context for this task.

- Before requesting clarification, carefully check the Semantic
  Model, Retrieved Context and Session Context.

- If the Semantic Model provides one clear mapping from the
  user's business term to a table, metric, dimension or column,
  treat that mapping as sufficient context. Do not ask the user
  to confirm the internal field name merely because the user
  used a business-friendly synonym.

- Clarification is required only when two or more plausible
  mappings remain after considering the original question,
  Semantic Model, Retrieved Context and Session Context.

- Do not ask the user for information that has already been
  supplied in Session Context.

- Ask only for information that is necessary to generate a
  reliable query.

- Prefer one concise clarification question that groups closely
  related missing information instead of asking many fragmented
  questions.
  
- Treat Session Context as authoritative information supplied
  by the user for the current task.

- Before asking for clarification, check whether the required
  information has already been supplied in Session Context.

- Do not repeat a clarification question that has already been
  answered by the user.
  
- Verified SQL examples are implementation references only.
  Do not use the business subject of a retrieved example as
  evidence that the user's ambiguous question refers to the
  same business subject.

Context sufficiency rules:

- Treat explicit business rules in Retrieved Context as
  authoritative for the current planning task.

- If the context explicitly defines a runtime convention such as
  “本期” = dt = 'p_month_yyyymm', apply it directly.
  Do not ask the user to provide the concrete date again.

- If a user-facing business term has exactly one clear mapping
  in the Semantic Model, use that mapping directly.
  Do not ask the user to confirm the internal table or column name.

- Clarification is required only when unresolved alternatives
  would materially change the business meaning or SQL result.


Clarification is only appropriate when the available context
still leaves two or more materially different interpretations
that would produce different business results.

Ambiguity rules:

- Do not arbitrarily choose between multiple plausible
  business subjects, tables, metrics, dimensions or business
  definitions.

- If two or more candidates are reasonably consistent with
  the original question and the supplied context does not
  clearly identify one of them, return need_clarification.

- A clarification question should identify the competing
  interpretations concisely so the user can choose between them.

- Do not treat a generic synonym as sufficient evidence when
  that synonym is shared by multiple business subjects.

- Prefer clarification over guessing when choosing the wrong
  business subject would materially change the query result.

Return JSON only.

If context is sufficient:
{{
  "status": "ready",
  "plan": {{
    "tables": ["table_name"],
    "dimensions": ["column_name"],
    "metrics": ["metric_name"],
    "filters": ["condition"],
    "group_by": ["column_name"],
    "requirements":["requirements"]
  }}
}}

If context is insufficient:

{{
  "status": "need_clarification",
  "clarification_question": "question to ask the user",
  "missing_context": [
    "missing information"
  ],
  "reason": "why this information is required"
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

    physical_schema = (
        render_linked_schema(
            linked_schema
        )
    )
    
    context_text = render_query_context(
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

Physical Schema rules:

- Use only physical tables and columns explicitly
  present in the supplied LinkedSchema.

- Do not invent physical table names or column names.

- The Semantic Model defines business meaning.

- LinkedSchema defines the physical schema available
  to this task.

- If Semantic Model and Physical Schema disagree
  about whether a physical table or column exists,
  do not invent a replacement.

- Prefer the fully qualified physical table name
  supplied by LinkedSchema.

{feedback_text}

Generate SQL only.
""".strip()