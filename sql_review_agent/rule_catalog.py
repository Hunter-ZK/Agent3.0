# sql_review_agent/rule_catalog.py

from sql_review_agent.llm.prompts import build_rule_issues_text
from sql_review_agent.rules.registry import RuleRegistry


def build_rule_catalog_text() -> str:
    return RuleRegistry().build_catalog_text()
