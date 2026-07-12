# sql_review_agent/llm/context_builder.py

from sql_review_agent.analysis.analyzer import analyze_sql
from sql_review_agent.metadata.provider import BaseMetadataProvider


def build_analysis_context_text(sql: str, dialect: str = "maxcompute") -> str:
    analysis = analyze_sql(sql, dialect=dialect)
    lines: list[str] = []

    lines.append("【SQL 结构分析】")
    lines.append(f"- Dialect: {analysis.dialect}")
    lines.append(f"- Statement Count: {len(analysis.statements)}")
    lines.append(f"- CTE Count: {len(analysis.ctes)}")
    lines.append("")

    if analysis.warnings:
        lines.append("【文本级风险】")
        for warning in analysis.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("【文件级特征】")
    for key, value in analysis.file_features.items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("【CTE 摘要】")
    if not analysis.ctes:
        lines.append("- 无 CTE")
    else:
        for cte_name, cte in analysis.ctes.items():
            lines.append(f"- CTE: {cte_name}")
            lines.append(f"  Output Columns: {', '.join(cte.output_columns) or 'UNKNOWN'}")
            refs = ", ".join(f"{item.relation_name}({item.relation_type})" for item in cte.referenced_relations)
            lines.append(f"  Referenced Relations: {refs or 'NONE'}")
    lines.append("")

    lines.append("【SQL 语句摘要】")
    for index, statement in enumerate(analysis.statements, start=1):
        lines.append(f"- Statement {index}")
        lines.append(f"  Type: {statement.statement_type}")
        lines.append(f"  Target Table: {statement.target_table or 'None'}")
        refs = ", ".join(f"{item.relation_name}({item.relation_type})" for item in statement.source_relations)
        lines.append(f"  Source Relations: {refs or 'NONE'}")
        feature_text = ", ".join(f"{key}={value}" for key, value in statement.features.items() if value)
        lines.append(f"  Features: {feature_text or 'None'}")

    return "\n".join(lines)


def build_metadata_context_text(sql: str, metadata_provider: BaseMetadataProvider | None) -> str:
    if metadata_provider is None:
        return "未启用元数据。"

    analysis = analyze_sql(sql)
    table_names: list[str] = []

    for statement in analysis.statements:
        if statement.target_table:
            table_names.append(statement.target_table)
        for relation in statement.source_relations:
            if relation.relation_type == "physical_table":
                table_names.append(relation.relation_name)

    table_names = list(dict.fromkeys(table_names))
    if not table_names:
        return "未解析到相关物理表。"

    lines: list[str] = ["【相关元数据】"]
    for table_name in table_names:
        table = metadata_provider.get_table(table_name)
        if table is None:
            lines.append(f"- Table: {table_name}")
            lines.append("  Metadata: NOT_FOUND")
            continue

        lines.append(f"- Table: {table.table_name}")
        lines.append(f"  Layer: {table.layer}")
        lines.append(f"  Comment: {table.comment}")
        lines.append(f"  Is Partitioned: {table.is_partitioned}")
        lines.append(f"  Partition Fields: {', '.join(table.partition_fields) or 'None'}")
        lines.append("  Columns:")
        for column in table.columns:
            lines.append(f"    - {column.name} ({column.data_type}): {column.comment}")

    return "\n".join(lines)
