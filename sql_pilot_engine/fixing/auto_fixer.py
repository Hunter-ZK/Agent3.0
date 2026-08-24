from __future__ import annotations

import re


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