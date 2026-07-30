# sql_review_agent/fixing/auto_fixer.py

import re

from sql_pilot_engine.analysis.parser import extract_insert_target_table
from sql_pilot_engine.core.models import FixedSqlResult, Issue
from sql_pilot_engine.metadata.provider import BaseMetadataProvider
from sql_pilot_engine.utils.sql_text import normalize_sql, replace_non_ascii_whitespace


def generate_fixed_sql(
    sql: str,
    issues: list[Issue],
    metadata_provider: BaseMetadataProvider | None = None,
) -> FixedSqlResult:
    fixed_sql = sql
    applied_fixes: list[str] = []
    manual_notes: list[str] = []
    issue_ids = {issue.rule_id for issue in issues}

    if "NON_ASCII_WHITESPACE" in issue_ids:
        fixed_sql = replace_non_ascii_whitespace(fixed_sql)
        applied_fixes.append("已将全角空格或不可见空白替换为普通空格。")

    if "MAXCOMPUTE_INSERT_OVERWRITE_TABLE_REQUIRED" in issue_ids:
        fixed_sql, changed = fix_insert_overwrite_missing_table(fixed_sql)
        if changed:
            applied_fixes.append("已补充 MaxCompute INSERT OVERWRITE TABLE 关键字。")

    if "DATAWORKS_HARDCODED_DATE" in issue_ids:
        fixed_sql, changed = fix_hardcoded_date(fixed_sql)
        if changed:
            applied_fixes.append("已将硬编码日期替换为 ${bizdate}。")

    if "INSERT_WITHOUT_PARTITION" in issue_ids:
        fixed_sql, changed, note = fix_insert_missing_partition(
            sql=fixed_sql,
            metadata_provider=metadata_provider,
        )
        if changed:
            applied_fixes.append(note)
        else:
            manual_notes.append(note)

    manual_notes.extend(build_manual_notes(issues))
    fixed_sql = append_manual_notes(sql=fixed_sql, manual_notes=manual_notes)

    return FixedSqlResult(
        fixed_sql=fixed_sql,
        applied_fixes=applied_fixes,
        manual_notes=manual_notes,
        source="auto",
    )


def fix_insert_overwrite_missing_table(sql: str) -> tuple[str, bool]:
    pattern = r"\binsert\s+overwrite\s+(?!table\b)"
    fixed_sql, count = re.subn(pattern, "insert overwrite table ", sql, count=0, flags=re.IGNORECASE)
    return fixed_sql, count > 0


def fix_hardcoded_date(sql: str) -> tuple[str, bool]:
    pattern = r"\b(ds|dt|biz_date|stat_date|pt|partition_date)\s*=\s*(['\"])\d{8}\2"

    def replace_date(match: re.Match) -> str:
        field_name = match.group(1)
        return f"{field_name} = '${{bizdate}}'"

    fixed_sql, count = re.subn(pattern, replace_date, sql, flags=re.IGNORECASE)
    return fixed_sql, count > 0


def fix_insert_missing_partition(
    sql: str,
    metadata_provider: BaseMetadataProvider | None,
) -> tuple[str, bool, str]:
    target_table = extract_insert_target_table(sql)

    if target_table is None:
        return sql, False, "AI_REVIEW_TODO: 无法解析 INSERT 目标表，未自动补充分区。"
    if metadata_provider is None:
        return sql, False, "AI_REVIEW_TODO: 未启用元数据，无法确认分区字段，未自动补充分区。"

    table = metadata_provider.get_table(target_table)
    if table is None:
        return sql, False, f"AI_REVIEW_TODO: 未找到目标表 {target_table} 的元数据，未自动补充分区。"
    if not table.is_partitioned:
        return sql, False, f"AI_REVIEW_TODO: 目标表 {target_table} 不是分区表，无需补充分区。"
    if not table.partition_fields:
        return sql, False, f"AI_REVIEW_TODO: 目标表 {target_table} 未配置分区字段，未自动补充分区。"
    if re.search(r"\bpartition\s*\(", normalize_sql(sql)):
        return sql, False, "AI_REVIEW_TODO: SQL 已存在 PARTITION，未重复添加。"

    partition_field = table.partition_fields[0]
    target_pattern = re.escape(target_table)
    # 对 qualified name 和 simple name 都做支持。
    simple_target_pattern = re.escape(target_table.split(".")[-1])
    pattern = rf"(\binsert\s+(overwrite|into)\s+table\s+({target_pattern}|{simple_target_pattern}))\b"
    replacement = rf"\1 partition({partition_field}='${{bizdate}}')"

    fixed_sql, count = re.subn(pattern, replacement, sql, count=1, flags=re.IGNORECASE)
    if count == 0:
        return sql, False, f"AI_REVIEW_TODO: 未能定位 INSERT 目标表 {target_table}，未自动补充分区。"

    return fixed_sql, True, f"已为分区表 {target_table} 补充 PARTITION({partition_field}='${{bizdate}}')。"


def build_manual_notes(issues: list[Issue]) -> list[str]:
    notes: list[str] = []
    for issue in issues:
        if issue.rule_id == "UNKNOWN_COLUMN":
            notes.append(f"AI_REVIEW_TODO: {issue.message} 请人工确认字段名或元数据。")
        elif issue.rule_id == "UNKNOWN_SOURCE_TABLE":
            notes.append(f"AI_REVIEW_TODO: {issue.message} 请人工确认表名或元数据。")
        elif issue.rule_id == "UNKNOWN_TABLE_ALIAS":
            notes.append(f"AI_REVIEW_TODO: {issue.message} 请人工确认表别名。")
        elif issue.rule_id.startswith("LLM_") and issue.rule_id != "LLM_REVIEW_FAILED":
            notes.append(f"AI_REVIEW_TODO: {issue.message} 建议人工复核。")
    return deduplicate_notes(notes)


def append_manual_notes(sql: str, manual_notes: list[str]) -> str:
    manual_notes = deduplicate_notes(manual_notes)
    if not manual_notes:
        return sql

    lines = [sql.rstrip(), "", "-- ================= AI REVIEW TODO ================="]
    for note in manual_notes:
        if note.startswith("AI_REVIEW_TODO"):
            lines.append(f"-- {note}")
        else:
            lines.append(f"-- AI_REVIEW_TODO: {note}")
    return "\n".join(lines) + "\n"


def deduplicate_notes(notes: list[str]) -> list[str]:
    return list(dict.fromkeys(notes))
