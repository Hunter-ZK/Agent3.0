# sql_review_agent/rules/base.py

from collections.abc import Callable
from dataclasses import dataclass

from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import Severity
from sql_pilot_engine.core.models import Issue

RuleCheckFunc = Callable[[str, ReviewContext], list[Issue]]


@dataclass
class Rule:
    rule_id: str
    name: str
    severity: Severity
    category: str
    description: str
    check: RuleCheckFunc
    modes: set[str]
    enabled: bool = True
