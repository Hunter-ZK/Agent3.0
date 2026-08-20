from __future__ import annotations

from typing import Protocol

from sql_pilot_engine.standards.models import (
    CanonicalRoot,
    StandardRule,
)

class StandardsProvider(Protocol):

    def get_rule(
        self,
        rule_code: str,
    ) -> StandardRule | None:
        ...

    def list_rules(
        self,
        *,
        category: str | None = None,
    ) -> tuple[StandardRule, ...]:
        ...

    def get_canonical_root(
        self,
        chinese_expression: str,
    ) -> CanonicalRoot | None:
        ...
