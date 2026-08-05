from __future__ import annotations

from sql_pilot_engine.analysis.parser import (
    extract_insert_target_table,
    has_partition_clause,
)
from sql_pilot_engine.core.context import (
    ReviewContext,
)
from sql_pilot_engine.core.enums import Severity
from sql_pilot_engine.core.models import Issue
from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)
from sql_pilot_engine.rules.base import Rule
from sql_pilot_engine.rules.basic import make_issue
from sql_pilot_engine.utils.sql_text import (
    normalize_sql,
)


def check_insert_without_partition(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:
    """检查分区表INSERT是否显式声明PARTITION。

    这个规则只负责“是否缺少PARTITION”。

    表不存在、字段不存在、元数据查询失败，
    统一交给MetadataValidator处理。
    """

    normalized_sql = normalize_sql(sql)

    if "insert " not in normalized_sql:
        return []

    if has_partition_clause(sql):
        return []

    target_table = extract_insert_target_table(
        sql
    )

    if target_table is None:
        return []

    metadata_provider = context.metadata_provider

    if metadata_provider is None:
        return [
            make_issue(
                rule_id=(
                    "INSERT_WITHOUT_PARTITION_"
                    "METADATA_UNKNOWN"
                ),
                title=(
                    "INSERT缺少PARTITION，"
                    "但未启用元数据"
                ),
                severity=Severity.MEDIUM,
                message=(
                    f"目标表 {target_table} "
                    "未声明PARTITION，"
                    "但当前无法确认该表"
                    "是否为分区表。"
                ),
                suggestion=(
                    "建议启用元数据检查；"
                    "如果目标表是分区表，"
                    "请显式声明PARTITION。"
                ),
                evidence=target_table,
                category="metadata",
            )
        ]

    lookup = metadata_provider.get_table(
        target_table
    )

    # NOT_FOUND和ERROR由MetadataValidator
    # 生成统一Issue，避免这里重复告警。
    if (
        lookup.status
        != MetadataLookupStatus.FOUND
        or lookup.table is None
    ):
        return []

    table = lookup.table

    if not table.is_partitioned:
        return []

    return [
        make_issue(
            rule_id="INSERT_WITHOUT_PARTITION",
            title="分区表INSERT缺少PARTITION",
            severity=Severity.HIGH,
            message=(
                f"目标表 {target_table} 是分区表，"
                "但INSERT语句未声明PARTITION。"
            ),
            suggestion=(
                "请在INSERT目标表后显式声明"
                "PARTITION，例如："
                "PARTITION(dt='${bizdate}')。"
            ),
            evidence=target_table,
            category="metadata",
        )
    ]


METADATA_RULES = [
    Rule(
        rule_id="INSERT_WITHOUT_PARTITION",
        name="Insert without partition",
        severity=Severity.HIGH,
        category="metadata",
        description=(
            "分区表INSERT需要声明PARTITION。"
        ),
        check=check_insert_without_partition,
        modes={
            "debug",
            "prod",
            "backfill",
        },
    ),
]