from sql_pilot_engine.core.context import (
    ReviewContext,
)
from sql_pilot_engine.core.models import (
    Issue,
)
from sql_pilot_engine.rules.safety import (
    SAFETY_RULES,
)

from sql_pilot_engine.rules.maxcompute import (
    MAXCOMPUTE_RULES,
)

class RuleRegistry:
    """规则注册表。"""

    def __init__(self) -> None:
        self.rules = [
            *SAFETY_RULES,
            *MAXCOMPUTE_RULES,
        ]
        self.register_many(
            BASIC_RULES
        )
        self.register_many(
            MAXCOMPUTE_RULES
        )
        self.register_many(
            METADATA_RULES
        )

    def register(
        self,
        rule: Rule,
    ) -> None:

        self.rules[
            rule.rule_id
        ] = rule

    def register_many(
        self,
        rules: list[Rule],
    ) -> None:

        for rule in rules:
            self.register(rule)

    def list_rules(
        self,
    ) -> list[Rule]:

        return list(
            self.rules.values()
        )

    def run(
        self,
        sql: str,
        context: ReviewContext,
        categories: (
            set[str] | None
        ) = None,
    ) -> list[Issue]:

        issues: list[Issue] = []

        for rule in (
            self.list_rules()
        ):
            if not rule.enabled:
                continue

            if (
                context.mode
                not in rule.modes
            ):
                continue

            if (
                categories is not None
                and rule.category
                not in categories
            ):
                continue

            issues.extend(
                rule.check(
                    sql,
                    context,
                )
            )

        return issues

    def build_catalog_text(
        self,
    ) -> str:

        lines: list[str] = []

        for rule in (
            self.list_rules()
        ):
            lines.append(
                f"- {rule.rule_id} "
                f"[{rule.category}/"
                f"{rule.severity.value}]: "
                f"{rule.description}"
            )

        return "\n".join(
            lines
        )