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


def check_drop_or_truncate(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:
    """阻断明确的 DROP / TRUNCATE 高危操作。"""

    _ = sql

    facts = context.sql_facts

    if facts is None:
        return []

    if (
        not facts.has_drop
        and not facts.has_truncate
    ):
        return []

    return [
        make_issue(
            rule_id="DROP_OR_TRUNCATE",
            title=(
                "检测到高危 "
                "DROP/TRUNCATE 操作"
            ),
            severity=Severity.HIGH,
            message=(
                "检测到 DROP TABLE "
                "或 TRUNCATE TABLE。"
            ),
            suggestion=(
                "该操作属于确定性高风险操作，"
                "必须阻断自动 Trusted 流程。"
            ),
            evidence=(
                "AST statement type: "
                "drop/truncate"
            ),
            category="safety",
            action=IssueAction.BLOCK,
        )
    ]


SAFETY_RULES = [
    Rule(
        rule_id="DROP_OR_TRUNCATE",
        name="Detect drop or truncate",
        severity=Severity.HIGH,
        category="safety",
        description=(
            "阻断 DROP/TRUNCATE 高危操作。"
        ),
        check=check_drop_or_truncate,
        modes={
            "debug",
            "prod",
            "backfill",
        },
    ),
]