import re

from sql_pilot_engine.core.context import (
    ReviewContext,
)
from sql_pilot_engine.core.enums import (
    IssueAction,
    Severity,
)
from sql_pilot_engine.core.models import (
    Issue,
)
from sql_pilot_engine.rules.base import (
    Rule,
)
from sql_pilot_engine.rules.helpers import (
    make_issue,
)
from sql_pilot_engine.utils.sql_text import (
    normalize_sql,
)


def check_insert_overwrite_requires_table(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:

    _ = context

    normalized = normalize_sql(
        sql
    )

    if not re.search(
        (
            r"\binsert\s+overwrite\s+"
            r"(?!table\b)"
        ),
        normalized,
    ):
        return []

    return [
        make_issue(
            rule_id=(
                "MAXCOMPUTE_"
                "INSERT_OVERWRITE_"
                "TABLE_REQUIRED"
            ),
            title=(
                "MaxCompute "
                "INSERT OVERWRITE "
                "缺少 TABLE 关键字"
            ),
            severity=Severity.HIGH,
            message=(
                "检测到 INSERT OVERWRITE "
                "后未使用 TABLE 关键字。"
            ),
            suggestion=(
                "改为 INSERT OVERWRITE "
                "TABLE 目标表 ..."
            ),
            evidence=(
                "INSERT OVERWRITE "
                "without TABLE"
            ),
            category="maxcompute",
            action=IssueAction.AUTO_FIX,
            auto_fixable=True,
        )
    ]


MAXCOMPUTE_RULES = [
    Rule(
        rule_id=(
            "MAXCOMPUTE_"
            "INSERT_OVERWRITE_"
            "TABLE_REQUIRED"
        ),
        name=(
            "MaxCompute INSERT "
            "OVERWRITE TABLE required"
        ),
        severity=Severity.HIGH,
        category="maxcompute",
        description=(
            "MaxCompute INSERT OVERWRITE "
            "使用 TABLE 关键字。"
        ),
        check=(
            check_insert_overwrite_requires_table
        ),
        modes={
            "debug",
            "prod",
            "backfill",
        },
    ),
]