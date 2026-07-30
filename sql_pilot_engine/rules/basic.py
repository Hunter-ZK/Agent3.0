# sql_review_agent/rules/basic.py

import re

from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import IssueSource, Severity
from sql_pilot_engine.core.models import Issue
from sql_pilot_engine.rules.base import Rule
from sql_pilot_engine.utils.sql_text import contains_non_ascii_whitespace, normalize_sql


def make_issue(rule_id: str, title: str, severity: Severity, message: str, suggestion: str, evidence: str, category: str) -> Issue:
    return Issue(
        rule_id=rule_id,
        title=title,
        severity=severity,
        message=message,
        suggestion=suggestion,
        evidence=evidence,
        category=category,
        source=IssueSource.RULE,
        confidence=1.0,
    )


def check_select_star(sql: str, context: ReviewContext) -> list[Issue]:
    normalized = normalize_sql(sql)
    if re.search(r"\bselect\s+\*", normalized):
        return [
            make_issue(
                rule_id="SELECT_STAR",
                title="避免使用 SELECT *",
                severity=Severity.MEDIUM,
                message="检测到 SELECT *，字段范围不可控，可能引入不必要的数据扫描。",
                suggestion="请显式声明需要查询的字段。",
                evidence="SELECT *",
                category="style",
            )
        ]
    return []


def check_drop_or_truncate(sql: str, context: ReviewContext) -> list[Issue]:
    normalized = normalize_sql(sql)
    if re.search(r"\b(drop\s+table|truncate\s+table)\b", normalized):
        return [
            make_issue(
                rule_id="DROP_OR_TRUNCATE",
                title="检测到高危 DROP/TRUNCATE 操作",
                severity=Severity.HIGH,
                message="检测到 DROP TABLE 或 TRUNCATE TABLE，生产环境执行前必须确认影响范围。",
                suggestion="请确认是否必须执行，并增加审批或备份流程。",
                evidence="DROP/TRUNCATE",
                category="safety",
            )
        ]
    return []


def check_non_ascii_whitespace(sql: str, context: ReviewContext) -> list[Issue]:
    if contains_non_ascii_whitespace(sql):
        return [
            make_issue(
                rule_id="NON_ASCII_WHITESPACE",
                title="检测到全角或不可见空白字符",
                severity=Severity.LOW,
                message="SQL 中包含全角空格或不可见空白，可能导致执行失败或难以排查。",
                suggestion="建议替换为普通空格。",
                evidence="non-ascii whitespace",
                category="style",
            )
        ]
    return []


BASIC_RULES = [
    Rule(
        rule_id="SELECT_STAR",
        name="Avoid SELECT star",
        severity=Severity.MEDIUM,
        category="style",
        description="避免使用 SELECT *。",
        check=check_select_star,
        modes={"debug", "prod", "backfill"},
    ),
    Rule(
        rule_id="DROP_OR_TRUNCATE",
        name="Detect drop or truncate",
        severity=Severity.HIGH,
        category="safety",
        description="检测 DROP/TRUNCATE 高危操作。",
        check=check_drop_or_truncate,
        modes={"debug", "prod", "backfill"},
    ),
    Rule(
        rule_id="NON_ASCII_WHITESPACE",
        name="Detect non-ascii whitespace",
        severity=Severity.LOW,
        category="style",
        description="检测全角或不可见空白。",
        check=check_non_ascii_whitespace,
        modes={"debug", "prod", "backfill"},
    ),
]
