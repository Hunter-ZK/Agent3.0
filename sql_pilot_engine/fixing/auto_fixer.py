from __future__ import annotations

import re

from sql_pilot_engine.core.models import (
    FixedSqlResult,
    Issue,
)


def generate_fixed_sql(
    sql: str,
    issues: list[Issue],
) -> FixedSqlResult:

    fixed_sql = sql

    applied_fixes: list[str] = []

    issue_ids = {
        issue.rule_id
        for issue
        in issues
    }

    if (
        "MAXCOMPUTE_"
        "INSERT_OVERWRITE_"
        "TABLE_REQUIRED"
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
                "INSERT OVERWRITE TABLE "
                "关键字。"
            )

    return FixedSqlResult(
        fixed_sql=fixed_sql,
        applied_fixes=(
            applied_fixes
        ),
        manual_notes=[],
        source="auto",
    )


def fix_insert_overwrite_missing_table(
    sql: str,
) -> tuple[str, bool]:

    pattern = (
        r"\binsert\s+overwrite\s+"
        r"(?!table\b)"
    )

    fixed_sql, count = (
        re.subn(
            pattern,
            "insert overwrite table ",
            sql,
            count=0,
            flags=re.IGNORECASE,
        )
    )

    return (
        fixed_sql,
        count > 0,
    )