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
from sql_pilot_engine.rules.text_to_sql import (
    TEXT_TO_SQL_RULES,
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

        self.register_many(
            TEXT_TO_SQL_RULES
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

        active_packs = {
            "base",
        }

        active_packs.update(
            context.rule_packs
            or ()
        )

        for rule in (
            self.list_rules()
        ):
            if not rule.enabled:
                continue

            if (
                rule.packs
                .isdisjoint(
                    active_packs
                )
            ):
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
        *,
        rule_packs: tuple[
            str,
            ...
        ] = (),
    ) -> str:
        """
        构建当前 Capability 实际可见的
        Deterministic Guardrail Catalog。

        base pack 永远可见；
        capability-specific rule
        只有显式启用对应 pack 时才暴露给 LLM。

        这样可以保证：
        Deterministic Rule 的作用域
        与 LLM Reviewer 看到的系统边界一致。
        """

        active_packs = {
            "base",
        }

        active_packs.update(
            rule_packs
            or ()
        )

        active_rules = [
            rule
            for rule
            in self.list_rules()
            if (
                rule.enabled
                and not (
                    rule.packs
                    .isdisjoint(
                        active_packs
                    )
                )
            )
        ]

        if not active_rules:
            return (
                "当前没有额外确定性 Guardrail。"
            )

        lines: list[str] = []

        for rule in active_rules:
            lines.append(
                f"- {rule.rule_id} "
                f"[{rule.category}/"
                f"{rule.severity.value}]: "
                f"{rule.description}"
            )

        return "\n".join(
            lines
        )