# sql_review_agent/rules/basic.py

import re

from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import IssueSource, Severity, IssueAction
from sql_pilot_engine.core.models import Issue
from sql_pilot_engine.rules.base import Rule
from sql_pilot_engine.utils.sql_text import contains_non_ascii_whitespace, normalize_sql


def make_issue(
        rule_id: str, 
        title: str, 
        severity: Severity, 
        message: str, 
        suggestion: str, 
        evidence: str, 
        category: str,
        *,
        action=IssueAction(
            IssueAction.HUMAN_REVIEW
        ),
        auto_fixable: bool = False,
        blocking: bool = False,
    ) -> Issue:
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
        action=action,
        auto_fixable=auto_fixable,
        blocking=blocking,
    )


def check_select_star(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:

    facts = context.sql_facts

    if (
        facts is None
        or not facts.has_select_star
    ):
        return []

    return [
        make_issue(
            rule_id="SELECT_STAR",
            title="检测到 SELECT *",
            severity=Severity.MEDIUM,
            message=(
                "SELECT * 可能增加扫描量，"
                "并使输出字段随表结构变化。"
            ),
            suggestion=(
                "如字段范围明确，建议显式声明需要的字段。"
            ),
            evidence=(
                "AST: Select projection contains Star"
            ),
            category="style",
            action=IssueAction.ADVISORY,
        )
    ]


def check_drop_or_truncate(sql: str, context: ReviewContext) -> list[Issue]:
    """通过语句类型识别DROP和TRUNCATE操作。"""
    
    facts = context.sql_facts
    
    if facts is None:
        return []
    
    if not facts.has_drop and not facts.has_truncate:
        return []
    
    return [
        make_issue(
            rule_id="DROP_OR_TRUNCATE",
            title="检测到高危 DROP/TRUNCATE 操作",
            severity=Severity.HIGH,
            message="检测到 DROP TABLE 或 TRUNCATE TABLE，生产环境执行前必须确认影响范围。",
            suggestion="请确认是否必须执行，并增加审批或备份流程。",
            evidence="AST statement type: drop/truncate",
            category="safety",
            action=IssueAction.BLOCK,
            auto_fixable=False,
            blocking=True,
        )
    ]



def check_non_ascii_whitespace(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:

    if not contains_non_ascii_whitespace(
        sql
    ):
        return []

    return [
        make_issue(
            rule_id="NON_ASCII_WHITESPACE",
            title="检测到全角或不可见空白字符",
            severity=Severity.LOW,
            message=(
                "SQL 中包含全角空格或不可见空白，"
                "可能导致执行失败或难以排查。"
            ),
            suggestion="替换为普通空格。",
            evidence="non-ascii whitespace",
            category="syntax",
            action=IssueAction.AUTO_FIX,
            auto_fixable=True,
        )
    ]

