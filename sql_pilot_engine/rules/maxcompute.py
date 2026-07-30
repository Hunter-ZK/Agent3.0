# sql_review_agent/rules/maxcompute.py

import re

from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import Severity
from sql_pilot_engine.core.models import Issue
from sql_pilot_engine.rules.base import Rule
from sql_pilot_engine.rules.basic import make_issue
from sql_pilot_engine.utils.sql_text import normalize_sql


def check_insert_overwrite_requires_table(sql: str, context: ReviewContext) -> list[Issue]:
    normalized = normalize_sql(sql)
    if re.search(r"\binsert\s+overwrite\s+(?!table\b)", normalized):
        return [
            make_issue(
                rule_id="MAXCOMPUTE_INSERT_OVERWRITE_TABLE_REQUIRED",
                title="MaxCompute INSERT OVERWRITE 缺少 TABLE 关键字",
                severity=Severity.HIGH,
                message="检测到 INSERT OVERWRITE 后未使用 TABLE 关键字，可能不符合 MaxCompute 语法要求。",
                suggestion="请改为：INSERT OVERWRITE TABLE 目标表名 ...",
                evidence="INSERT OVERWRITE without TABLE",
                category="maxcompute",
            )
        ]
    return []


def check_dataworks_hardcoded_date(sql: str, context: ReviewContext) -> list[Issue]:
    if context.mode == "backfill":
        return []

    normalized = normalize_sql(sql)
    pattern = r"\b(ds|dt|biz_date|stat_date|pt|partition_date)\s*=\s*(['\"])\d{8}\2"
    if re.search(pattern, normalized):
        return [
            make_issue(
                rule_id="DATAWORKS_HARDCODED_DATE",
                title="检测到 DataWorks 硬编码日期",
                severity=Severity.MEDIUM,
                message="检测到分区字段使用固定日期，周期任务中可能需要每天手工修改。",
                suggestion="建议将固定日期替换为 DataWorks 调度参数，例如 ${bizdate} 或项目约定参数。",
                evidence="partition_date = 'yyyyMMdd'",
                category="dataworks",
            )
        ]
    return []


MAXCOMPUTE_RULES = [
    Rule(
        rule_id="MAXCOMPUTE_INSERT_OVERWRITE_TABLE_REQUIRED",
        name="MaxCompute INSERT OVERWRITE TABLE required",
        severity=Severity.HIGH,
        category="maxcompute",
        description="MaxCompute INSERT OVERWRITE 建议显式使用 TABLE。",
        check=check_insert_overwrite_requires_table,
        modes={"debug", "prod", "backfill"},
    ),
    Rule(
        rule_id="DATAWORKS_HARDCODED_DATE",
        name="DataWorks hardcoded date",
        severity=Severity.MEDIUM,
        category="dataworks",
        description="周期任务中避免硬编码日期。",
        check=check_dataworks_hardcoded_date,
        modes={"debug", "prod"},
    ),
]
