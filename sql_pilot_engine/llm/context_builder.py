from __future__ import annotations

from sql_pilot_engine.analysis.sql_analysis import SQLAnalysisAdapter
from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)
from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)


def build_analysis_context_text(
    sql: str,
    dialect: str = "maxcompute",
) -> str:
    """将SQL结构分析结果转换为LLM可读取的文本。"""

    analysis = analyze_sql(
        sql,
        dialect=dialect,
    )

    lines: list[str] = []

    lines.append("【SQL 结构分析】")
    lines.append(f"- Dialect: {analysis.dialect}")
    lines.append(
        f"- Statement Count: "
        f"{len(analysis.statements)}"
    )
    lines.append(
        f"- CTE Count: {len(analysis.ctes)}"
    )
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
            lines.append(
                "  Output Columns: "
                f"{', '.join(cte.output_columns) or 'UNKNOWN'}"
            )

            references = ", ".join(
                (
                    f"{item.relation_name}"
                    f"({item.relation_type})"
                )
                for item in cte.referenced_relations
            )

            lines.append(
                "  Referenced Relations: "
                f"{references or 'NONE'}"
            )

    lines.append("")

    lines.append("【SQL 语句摘要】")

    for index, statement in enumerate(
        analysis.statements,
        start=1,
    ):
        lines.append(f"- Statement {index}")
        lines.append(
            f"  Type: {statement.statement_type}"
        )
        lines.append(
            "  Target Table: "
            f"{statement.target_table or 'None'}"
        )

        references = ", ".join(
            (
                f"{item.relation_name}"
                f"({item.relation_type})"
            )
            for item in statement.source_relations
        )

        lines.append(
            "  Source Relations: "
            f"{references or 'NONE'}"
        )

        feature_text = ", ".join(
            f"{key}={value}"
            for key, value
            in statement.features.items()
            if value
        )

        lines.append(
            f"  Features: {feature_text or 'None'}"
        )

    return "\n".join(lines)


def build_metadata_context_text(
    sql: str,
    metadata_provider: MetadataProvider | None,
) -> str:
    """将SQL涉及的元数据转换为LLM上下文。

    Provider始终返回TableLookupResult，因此这里必须分别处理：

    FOUND：
        查询成功，并且找到表。

    NOT_FOUND：
        查询成功，但目标表不存在。

    ERROR：
        查询过程失败，不能误报为表不存在。
    """

    if metadata_provider is None:
        return "未启用元数据。"

    analysis = analyze_sql(sql)

    table_names: list[str] = []

    for statement in analysis.statements:
        if statement.target_table:
            table_names.append(
                statement.target_table
            )

        for relation in statement.source_relations:
            if (
                relation.relation_type
                == "physical_table"
            ):
                table_names.append(
                    relation.relation_name
                )

    # 字典Key不能重复，并且会保留插入顺序。
    table_names = list(
        dict.fromkeys(table_names)
    )

    if not table_names:
        return "未解析到相关物理表。"

    lines: list[str] = ["【相关元数据】"]

    for table_name in table_names:
        lookup = metadata_provider.get_table(
            table_name
        )

        if (
            lookup.status
            == MetadataLookupStatus.ERROR
        ):
            lines.append(
                f"- Table: {table_name}"
            )
            lines.append(
                "  Metadata: ERROR"
            )
            lines.append(
                "  Error: "
                f"{lookup.error_message or 'unknown error'}"
            )
            continue

        if (
            lookup.status
            == MetadataLookupStatus.NOT_FOUND
        ):
            lines.append(
                f"- Table: {table_name}"
            )
            lines.append(
                "  Metadata: NOT_FOUND"
            )
            continue

        # FOUND状态按契约应当携带TableMetadata。
        # 这里仍然进行防御性检查，避免错误Provider
        # 让上下文构造过程直接崩溃。
        if lookup.table is None:
            lines.append(
                f"- Table: {table_name}"
            )
            lines.append(
                "  Metadata: INVALID_RESULT"
            )
            continue

        table = lookup.table

        lines.append(
            f"- Table: {table.full_name}"
        )
        lines.append(
            f"  Description: {table.description}"
        )
        lines.append(
            f"  Is Partitioned: "
            f"{table.is_partitioned}"
        )
        lines.append(
            "  Partition Fields: "
            f"{', '.join(table.partition_fields) or 'None'}"
        )
        lines.append("  Columns:")

        # table.columns是字段名到ColumnMetadata的映射。
        # 遍历values()才能得到字段元数据对象。
        for column in table.columns.values():
            lines.append(
                f"    - {column.name} "
                f"({column.data_type}): "
                f"{column.description}"
            )

    return "\n".join(lines)