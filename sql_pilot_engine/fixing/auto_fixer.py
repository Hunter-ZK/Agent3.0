from __future__ import annotations

import re

from sql_pilot_engine.analysis.parser import (
    extract_insert_target_table,
)
from sql_pilot_engine.core.models import (
    FixedSqlResult,
    Issue,
)
from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)
from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)
from sql_pilot_engine.utils.sql_text import (
    normalize_sql,
    replace_non_ascii_whitespace,
)


def generate_fixed_sql(
    sql: str,
    issues: list[Issue],
    metadata_provider: MetadataProvider | None = None,
) -> FixedSqlResult:
    fixed_sql = sql
    applied_fixes: list[str] = []
    manual_notes: list[str] = []

    issue_ids = {
        issue.rule_id
        for issue in issues
    }

    if "NON_ASCII_WHITESPACE" in issue_ids:
        fixed_sql = replace_non_ascii_whitespace(
            fixed_sql
        )
        applied_fixes.append(
            "已将全角空格或不可见空白"
            "替换为普通空格。"
        )

    if (
        "MAXCOMPUTE_INSERT_OVERWRITE_TABLE_REQUIRED"
        in issue_ids
    ):
        fixed_sql, changed = (
            fix_insert_overwrite_missing_table(
                fixed_sql
            )
        )

        if changed:
            applied_fixes.append(
                "已补充 MaxCompute "
                "INSERT OVERWRITE TABLE 关键字。"
            )

    if "DATAWORKS_HARDCODED_DATE" in issue_ids:
        fixed_sql, changed = fix_hardcoded_date(
            fixed_sql
        )

        if changed:
            applied_fixes.append(
                "已将硬编码日期替换为 ${bizdate}。"
            )

    if "INSERT_WITHOUT_PARTITION" in issue_ids:
        fixed_sql, changed, note = (
            fix_insert_missing_partition(
                sql=fixed_sql,
                metadata_provider=(
                    metadata_provider
                ),
            )
        )

        if changed:
            applied_fixes.append(note)
        else:
            manual_notes.append(note)

    manual_notes.extend(
        build_manual_notes(issues)
    )

    fixed_sql = append_manual_notes(
        sql=fixed_sql,
        manual_notes=manual_notes,
    )

    return FixedSqlResult(
        fixed_sql=fixed_sql,
        applied_fixes=applied_fixes,
        manual_notes=manual_notes,
        source="auto",
    )


def fix_insert_overwrite_missing_table(
    sql: str,
) -> tuple[str, bool]:
    pattern = (
        r"\binsert\s+overwrite\s+(?!table\b)"
    )

    fixed_sql, count = re.subn(
        pattern,
        "insert overwrite table ",
        sql,
        count=0,
        flags=re.IGNORECASE,
    )

    return fixed_sql, count > 0


def fix_hardcoded_date(
    sql: str,
) -> tuple[str, bool]:
    pattern = (
        r"\b(ds|dt|biz_date|stat_date|pt|"
        r"partition_date)\s*=\s*"
        r"(['\"])\d{8}\2"
    )

    def replace_date(
        match: re.Match[str],
    ) -> str:
        field_name = match.group(1)

        return (
            f"{field_name} = "
            f"'${{bizdate}}'"
        )

    fixed_sql, count = re.subn(
        pattern,
        replace_date,
        sql,
        flags=re.IGNORECASE,
    )

    return fixed_sql, count > 0


def fix_insert_missing_partition(
    sql: str,
    metadata_provider: MetadataProvider | None,
) -> tuple[str, bool, str]:
    """根据目标表元数据自动补充分区声明。

    返回值：
        第一个值是修复后的SQL；
        第二个值表示SQL是否发生修改；
        第三个值是修复说明或人工处理说明。
    """

    target_table = extract_insert_target_table(
        sql
    )

    if target_table is None:
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            "无法解析 INSERT 目标表，"
            "未自动补充分区。",
        )

    if metadata_provider is None:
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            "未启用元数据，"
            "无法确认分区字段。",
        )

    lookup = metadata_provider.get_table(
        target_table
    )

    if (
        lookup.status
        == MetadataLookupStatus.ERROR
    ):
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            f"查询目标表 {target_table} "
            "的元数据失败："
            f"{lookup.error_message or 'unknown error'}。",
        )

    if (
        lookup.status
        == MetadataLookupStatus.NOT_FOUND
    ):
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            f"未找到目标表 {target_table} "
            "的元数据，未自动补充分区。",
        )

    if lookup.table is None:
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            f"目标表 {target_table} 的元数据"
            "返回结果不完整，未自动补充分区。",
        )

    table = lookup.table

    if not table.is_partitioned:
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            f"目标表 {target_table} "
            "不是分区表，无需补充分区。",
        )

    if re.search(
        r"\bpartition\s*\(",
        normalize_sql(sql),
    ):
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            "SQL 已存在 PARTITION，"
            "未重复添加。",
        )

    partition_field = table.partition_fields[0]

    qualified_target = re.escape(
        target_table
    )
    simple_target = re.escape(
        target_table.split(".")[-1]
    )

    pattern = (
        rf"(\binsert\s+(overwrite|into)\s+table\s+"
        rf"({qualified_target}|{simple_target}))\b"
    )

    replacement = (
        rf"\1 partition("
        rf"{partition_field}='${{bizdate}}')"
    )

    fixed_sql, count = re.subn(
        pattern,
        replacement,
        sql,
        count=1,
        flags=re.IGNORECASE,
    )

    if count == 0:
        return (
            sql,
            False,
            "AI_REVIEW_TODO: "
            f"未能定位 INSERT 目标表 "
            f"{target_table}，"
            "未自动补充分区。",
        )

    return (
        fixed_sql,
        True,
        f"已为分区表 {target_table} 补充 "
        f"PARTITION("
        f"{partition_field}='${{bizdate}}')。",
    )


def build_manual_notes(
    issues: list[Issue],
) -> list[str]:
    notes: list[str] = []

    for issue in issues:
        if issue.rule_id == "COLUMN_NOT_FOUND":
            notes.append(
                "AI_REVIEW_TODO: "
                f"{issue.message} "
                "请人工确认字段名或元数据。"
            )

        elif issue.rule_id == "TABLE_NOT_FOUND":
            notes.append(
                "AI_REVIEW_TODO: "
                f"{issue.message} "
                "请人工确认表名或元数据。"
            )

        elif issue.rule_id == "METADATA_LOOKUP_FAILED":
            notes.append(
                "AI_REVIEW_TODO: "
                f"{issue.message} "
                "请检查元数据服务。"
            )

        elif (
            issue.rule_id.startswith("LLM_")
            and issue.rule_id
            != "LLM_REVIEW_FAILED"
        ):
            notes.append(
                "AI_REVIEW_TODO: "
                f"{issue.message} "
                "建议人工复核。"
            )

    return deduplicate_notes(notes)


def append_manual_notes(
    sql: str,
    manual_notes: list[str],
) -> str:
    manual_notes = deduplicate_notes(
        manual_notes
    )

    if not manual_notes:
        return sql

    lines = [
        sql.rstrip(),
        "",
        (
            "-- ================= "
            "AI REVIEW TODO "
            "================="
        ),
    ]

    for note in manual_notes:
        if note.startswith("AI_REVIEW_TODO"):
            lines.append(f"-- {note}")
        else:
            lines.append(
                f"-- AI_REVIEW_TODO: {note}"
            )

    return "\n".join(lines) + "\n"


def deduplicate_notes(
    notes: list[str],
) -> list[str]:
    return list(
        dict.fromkeys(notes)
    )