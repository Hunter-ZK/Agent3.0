# sql_review_agent/rules/metadata.py

from sql_pilot_engine.analysis.parser import (
    extract_cte_names,
    extract_insert_target_table,
    extract_select_column_references,
    extract_source_tables,
    extract_table_aliases,
    has_partition_clause,
)
from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import Severity
from sql_pilot_engine.core.models import Issue
from sql_pilot_engine.rules.base import Rule
from sql_pilot_engine.rules.basic import make_issue
from sql_pilot_engine.utils.sql_text import normalize_sql


def check_insert_without_partition(sql: str, context: ReviewContext) -> list[Issue]:
    normalized = normalize_sql(sql)
    if "insert " not in normalized:
        return []

    if has_partition_clause(sql):
        return []

    target_table = extract_insert_target_table(sql)
    if target_table is None:
        return []

    metadata_provider = context.metadata_provider

    if metadata_provider is None:
        return [
            make_issue(
                rule_id="INSERT_WITHOUT_PARTITION_METADATA_UNKNOWN",
                title="INSERT 缺少 PARTITION，但未启用元数据",
                severity=Severity.MEDIUM,
                message=f"目标表 {target_table} 未声明 PARTITION，但当前无法确认该表是否为分区表。",
                suggestion="建议启用元数据检查；如果目标表是分区表，请显式声明 PARTITION。",
                evidence=target_table,
                category="metadata",
            )
        ]

    table = metadata_provider.get_table(target_table)

    if table is None:
        return [
            make_issue(
                rule_id="INSERT_TARGET_TABLE_METADATA_NOT_FOUND",
                title="INSERT 目标表元数据不存在",
                severity=Severity.MEDIUM,
                message=f"未找到目标表 {target_table} 的元数据，无法判断是否需要 PARTITION。",
                suggestion="请确认目标表是否存在，或补充元数据。",
                evidence=target_table,
                category="metadata",
            )
        ]

    if not table.is_partitioned:
        return []

    return [
        make_issue(
            rule_id="INSERT_WITHOUT_PARTITION",
            title="分区表 INSERT 缺少 PARTITION",
            severity=Severity.HIGH,
            message=f"目标表 {target_table} 是分区表，但 INSERT 语句未声明 PARTITION。",
            suggestion="请在 INSERT 目标表后显式声明 PARTITION，例如 PARTITION(dt='${bizdate}')。",
            evidence=target_table,
            category="metadata",
        )
    ]


def check_unknown_source_tables(sql: str, context: ReviewContext) -> list[Issue]:
    metadata_provider = context.metadata_provider
    if metadata_provider is None:
        return []

    cte_names = extract_cte_names(sql)
    issues: list[Issue] = []

    for table_name in extract_source_tables(sql):
        if table_name in cte_names:
            continue
        if not metadata_provider.table_exists(table_name):
            issues.append(
                make_issue(
                    rule_id="UNKNOWN_SOURCE_TABLE",
                    title="源表元数据不存在",
                    severity=Severity.MEDIUM,
                    message=f"源表 {table_name} 未在元数据中找到。",
                    suggestion="请确认表名是否正确，或补充元数据。",
                    evidence=table_name,
                    category="metadata",
                )
            )

    return issues


def check_unknown_select_columns(sql: str, context: ReviewContext) -> list[Issue]:
    metadata_provider = context.metadata_provider
    if metadata_provider is None:
        return []

    refs = extract_select_column_references(sql)
    if not refs:
        return []

    alias_map = extract_table_aliases(sql)
    source_tables = [table for table in extract_source_tables(sql) if table not in extract_cte_names(sql)]
    issues: list[Issue] = []

    for ref in refs:
        if ref.column_name == "*":
            continue

        if ref.table_alias:
            target_table = alias_map.get(ref.table_alias)
            if target_table is None:
                issues.append(
                    make_issue(
                        rule_id="UNKNOWN_TABLE_ALIAS",
                        title="未知表别名",
                        severity=Severity.MEDIUM,
                        message=f"字段引用 {ref.expression} 使用了未知别名 {ref.table_alias}。",
                        suggestion="请确认表别名是否正确。",
                        evidence=ref.expression,
                        category="metadata",
                    )
                )
                continue

            if not metadata_provider.table_exists(target_table):
                continue

            if not metadata_provider.column_exists(target_table, ref.column_name):
                issues.append(
                    make_issue(
                        rule_id="UNKNOWN_COLUMN",
                        title="字段元数据不存在",
                        severity=Severity.MEDIUM,
                        message=f"表 {target_table} 中未找到字段 {ref.column_name}。",
                        suggestion="请确认字段名是否正确，或补充元数据。",
                        evidence=ref.expression,
                        category="metadata",
                    )
                )
            continue

        if len(source_tables) != 1:
            continue

        target_table = source_tables[0]
        if metadata_provider.table_exists(target_table) and not metadata_provider.column_exists(target_table, ref.column_name):
            issues.append(
                make_issue(
                    rule_id="UNKNOWN_COLUMN",
                    title="字段元数据不存在",
                    severity=Severity.MEDIUM,
                    message=f"表 {target_table} 中未找到字段 {ref.column_name}。",
                    suggestion="请确认字段名是否正确，或补充元数据。",
                    evidence=ref.expression,
                    category="metadata",
                )
            )

    return issues


METADATA_RULES = [
    Rule(
        rule_id="INSERT_WITHOUT_PARTITION",
        name="Insert without partition",
        severity=Severity.HIGH,
        category="metadata",
        description="分区表 INSERT 需要声明 PARTITION。",
        check=check_insert_without_partition,
        modes={"debug", "prod", "backfill"},
    ),
    Rule(
        rule_id="UNKNOWN_SOURCE_TABLE",
        name="Unknown source table",
        severity=Severity.MEDIUM,
        category="metadata",
        description="检查源表是否存在于元数据。",
        check=check_unknown_source_tables,
        modes={"debug", "prod", "backfill"},
    ),
    Rule(
        rule_id="UNKNOWN_COLUMN",
        name="Unknown column",
        severity=Severity.MEDIUM,
        category="metadata",
        description="检查 SELECT 字段是否存在于元数据。",
        check=check_unknown_select_columns,
        modes={"debug", "prod", "backfill"},
    ),
]
