from sql_pilot_engine.core.context import (
    ReviewContext,
)
from sql_pilot_engine.core.models import (
    Issue,
)
from sql_pilot_engine.rules.base import (
    Rule,
)
from sql_pilot_engine.rules.maxcompute import (
    MAXCOMPUTE_RULES,
)
from sql_pilot_engine.rules.safety import (
    SAFETY_RULES,
)


class RuleRegistry:
    """确定性 SQL Guardrail 注册表。"""

    def __init__(self) -> None:
        self.rules: dict[
            str,
            Rule,
        ] = {}

        self.register_many(
            SAFETY_RULES
        )

        self.register_many(
            MAXCOMPUTE_RULES
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
            self.register(
                rule
            )

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
        """提供给 LLM 的系统硬边界，不是完整 Review Checklist。"""

        if not self.rules:
            return (
                "当前没有额外确定性 Guardrail。"
            )

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