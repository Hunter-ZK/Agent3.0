from __future__ import annotations

from sql_pilot_engine.analysis.facts import (
    SQLFacts,
)
from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)
from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)


def build_analysis_context_text(
    *,
    facts: SQLFacts,
    dialect: str = "maxcompute",
) -> str:
    """
    将已经提取完成的 SQLFacts
    转换为 LLM 可读取的结构分析文本。

    重要：

    本函数不重新解析 SQL。

    SQL 的唯一分析入口是：

        SQLParser
        → SQLAnalysisAdapter
        → SQLFacts

    LLM Context Builder 只消费 Facts。
    """

    lines: list[str] = []

    # ========================================================
    # Basic
    # ========================================================

    lines.append(
        "## SQL 结构分析"
    )

    lines.append(
        f"- Dialect: {dialect}"
    )

    lines.append(
        "- Statement Count: "
        f"{facts.statement_count}"
    )

    lines.append(
        "- Statement Types: "
        + (
            ", ".join(
                facts.statement_types
            )
            or "UNKNOWN"
        )
    )

    lines.append("")

    # ========================================================
    # CTE
    # ========================================================

    lines.append(
        "## CTE 摘要"
    )

    if not facts.cte_names:
        lines.append(
            "- 无 CTE"
        )

    else:
        lines.append(
            "- CTEs: "
            + ", ".join(
                facts.cte_names
            )
        )

    lines.append("")

    # ========================================================
    # Tables
    # ========================================================

    lines.append(
        "## 表引用"
    )

    if facts.target_tables:
        lines.append(
            "- Target Tables: "
            + ", ".join(
                facts.target_tables
            )
        )

    else:
        lines.append(
            "- Target Tables: None"
        )

    if facts.source_tables:
        lines.append(
            "- Source Tables: "
            + ", ".join(
                facts.source_tables
            )
        )

    else:
        lines.append(
            "- Source Tables: None"
        )

    lines.append("")

    # ========================================================
    # Table References
    # ========================================================

    lines.append(
        "## 表引用明细"
    )

    if not facts.table_references:
        lines.append(
            "- None"
        )

    else:
        for reference in (
            facts.table_references
        ):
            if reference.alias:
                lines.append(
                    "- "
                    f"{reference.physical_name} "
                    f"AS {reference.alias}"
                )

            else:
                lines.append(
                    "- "
                    f"{reference.physical_name}"
                )

    lines.append("")

    # ========================================================
    # Columns
    # ========================================================

    lines.append(
        "## 字段引用"
    )

    if not facts.column_references:
        lines.append(
            "- None"
        )

    else:
        for reference in (
            facts.column_references
        ):
            if reference.qualifier:
                lines.append(
                    "- "
                    f"{reference.qualifier}."
                    f"{reference.name}"
                )

            else:
                lines.append(
                    f"- {reference.name}"
                )

    lines.append("")

    # ========================================================
    # Select Aliases
    # ========================================================

    lines.append(
        "## SELECT 别名"
    )

    if facts.select_aliases:
        lines.append(
            "- "
            + ", ".join(
                facts.select_aliases
            )
        )

    else:
        lines.append(
            "- None"
        )

    lines.append("")

    # ========================================================
    # Structural Facts
    # ========================================================

    lines.append(
        "## SQL 特征"
    )

    lines.append(
        "- Has SELECT *: "
        f"{facts.has_select_star}"
    )

    lines.append(
        "- Has DROP: "
        f"{facts.has_drop}"
    )

    lines.append(
        "- Has TRUNCATE: "
        f"{facts.has_truncate}"
    )

    lines.append(
        "- Has Write Operation: "
        f"{facts.has_write_operation}"
    )

    # 下面两个字段是你此次
    # parser → SQLFacts 迁移新增的 INSERT Facts。
    #
    # 如果已经存在，就直接输出。
    insert_target_table = facts.insert_target_table

    has_partition_clause = facts.has_partition_clause

    if insert_target_table is not None:
        lines.append(
            "- Insert Target Table: "
            f"{insert_target_table}"
        )

        lines.append(
            "- Has Partition Clause: "
            f"{has_partition_clause}"
        )

    return "\n".join(
        lines
    )


def build_metadata_context_text(
    *,
    facts: SQLFacts,
    metadata_provider: (
        MetadataProvider | None
    ),
) -> str:
    """
    将 SQLFacts 中涉及的物理表
    转换为 LLM 可读取的元数据上下文。

    本函数同样禁止重新解析 SQL。
    """

    if metadata_provider is None:
        return "未启用元数据。"

    # ========================================================
    # Physical Tables
    # ========================================================

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

    # ========================================================
    # Metadata Rendering
    # ========================================================

    lines: list[str] = [
        "## 相关元数据"
    ]

    for table_name in table_names:

        lookup = (
            metadata_provider.get_table(
                table_name
            )
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

        # FOUND 状态按契约
        # 应当携带 TableMetadata。
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
            "  Description: "
            f"{table.description}"
        )

        lines.append(
            "  Is Partitioned: "
            f"{table.is_partitioned}"
        )

        lines.append(
            "  Partition Fields: "
            + (
                ", ".join(
                    table.partition_fields
                )
                or "None"
            )
        )

        lines.append(
            "  Columns:"
        )

        for column in (
            table.columns.values()
        ):
            lines.append(
                "    - "
                f"{column.name} "
                f"({column.data_type}): "
                f"{column.description}"
            )

    return "\n".join(
        lines
    )