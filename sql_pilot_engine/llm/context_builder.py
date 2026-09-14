from __future__ import annotations

from sql_pilot_engine.analysis.facts import SQLFacts
from sql_pilot_engine.metadata.models import MetadataLookupStatus
from sql_pilot_engine.metadata.provider import MetadataProvider


def build_analysis_context_text(
    *,
    facts: SQLFacts,
    dialect: str = "maxcompute",
) -> str:
    """Render already-derived SQL facts for LLM consumption without re-parsing SQL."""

    lines: list[str] = []
    lines.append("## SQL 结构分析")
    lines.append(f"- Dialect: {dialect}")
    lines.append(f"- Statement Count: {facts.statement_count}")
    lines.append(
        "- Statement Types: "
        + (", ".join(facts.statement_types) or "UNKNOWN")
    )
    lines.append("")

    lines.append("## CTE 摘要")
    if not facts.cte_names:
        lines.append("- 无 CTE")
    else:
        lines.append("- CTEs: " + ", ".join(facts.cte_names))
    lines.append("")

    lines.append("## 表引用")
    if facts.target_tables:
        lines.append("- Target Tables: " + ", ".join(facts.target_tables))
    else:
        lines.append("- Target Tables: None")

    if facts.source_tables:
        lines.append("- Source Tables: " + ", ".join(facts.source_tables))
    else:
        lines.append("- Source Tables: None")
    lines.append("")

    lines.append("## 表引用明细")
    if not facts.table_references:
        lines.append("- None")
    else:
        for reference in facts.table_references:
            if reference.alias:
                lines.append(
                    f"- {reference.physical_name} AS {reference.alias}"
                )
            else:
                lines.append(f"- {reference.physical_name}")
    lines.append("")

    lines.append("## 字段引用")
    if not facts.column_references:
        lines.append("- None")
    else:
        for reference in facts.column_references:
            if reference.qualifier:
                lines.append(f"- {reference.qualifier}.{reference.name}")
            else:
                lines.append(f"- {reference.name}")
    lines.append("")

    lines.append("## SELECT 别名")
    if facts.select_aliases:
        lines.append("- " + ", ".join(facts.select_aliases))
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## SQL 特征")
    lines.append(f"- Has SELECT *: {facts.has_select_star}")
    lines.append(f"- Has DROP: {facts.has_drop}")
    lines.append(f"- Has TRUNCATE: {facts.has_truncate}")
    lines.append(f"- Has Write Operation: {facts.has_write_operation}")

    insert_target_table = facts.insert_target_table
    if insert_target_table is not None:
        lines.append(f"- Insert Target Table: {insert_target_table}")
        lines.append(
            f"- Has Partition Clause: {facts.has_partition_clause}"
        )

    return "\n".join(lines)


def build_metadata_context_text(
    *,
    facts: SQLFacts,
    metadata_provider: MetadataProvider | None,
) -> str:
    """Render physical metadata referenced by SQLFacts for LLM review context."""

    if metadata_provider is None:
        return "未启用元数据。"

    table_names = list(
        dict.fromkeys(
            (
                *facts.target_tables,
                *facts.source_tables,
            )
        )
    )

    if not table_names:
        return "未解析到相关物理表。"

    lines: list[str] = ["## 相关元数据"]

    for table_name in table_names:
        lookup = metadata_provider.get_table(table_name)

        if lookup.status == MetadataLookupStatus.ERROR:
            lines.append(f"- Table: {table_name}")
            lines.append("  Metadata: ERROR")
            lines.append(
                "  Error: "
                f"{lookup.error_message or 'unknown error'}"
            )
            continue

        if lookup.status == MetadataLookupStatus.NOT_FOUND:
            lines.append(f"- Table: {table_name}")
            lines.append("  Metadata: NOT_FOUND")
            continue

        if lookup.table is None:
            lines.append(f"- Table: {table_name}")
            lines.append("  Metadata: INVALID_RESULT")
            continue

        table = lookup.table
        lines.append(f"- Table: {table.full_name}")
        lines.append(
            "  Description: "
            f"{table.business.description}"
        )

        partition_fields = table.technical.partition_fields
        if partition_fields:
            lines.append("  Is Partitioned: True")
            lines.append(
                "  Partition Fields: "
                + ", ".join(partition_fields)
            )

        lines.append("  Columns:")
        for column in table.columns.values():
            lines.append(
                "    - "
                f"{column.name} "
                f"({column.technical.data_type}): "
                f"{column.business.description}"
            )

    return "\n".join(lines)
