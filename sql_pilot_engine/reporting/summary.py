# sql_review_agent/reporting/summary.py

from sql_pilot_engine.core.enums import Severity
from sql_pilot_engine.core.models import Issue, ReviewResult


def count_by_severity(issues: list[Issue]) -> dict[str, int]:
    counts = {Severity.HIGH.value: 0, Severity.MEDIUM.value: 0, Severity.LOW.value: 0}
    for issue in issues:
        counts[issue.severity.value] += 1
    return counts


def build_overall_conclusion(result: ReviewResult) -> str:
    counts = count_by_severity(result.issues)
    high_count = counts[Severity.HIGH.value]
    medium_count = counts[Severity.MEDIUM.value]
    low_count = counts[Severity.LOW.value]

    if high_count > 0:
        return f"该 SQL 存在 {high_count} 个高风险问题、{medium_count} 个中风险问题、{low_count} 个低风险问题，不建议直接发布到生产环境。"
    if medium_count > 0:
        return f"该 SQL 存在 {medium_count} 个中风险问题、{low_count} 个低风险问题，建议修复后再发布。"
    if low_count > 0:
        return f"该 SQL 存在 {low_count} 个低风险提示，整体风险较低，但建议确认后再发布。"
    return "该 SQL 未发现明显风险。"


def select_top_risks(issues: list[Issue], limit: int = 5) -> list[Issue]:
    severity_rank = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}
    source_rank = {"rule": 3, "system": 2, "llm": 1}
    return sorted(
        issues,
        key=lambda issue: (-severity_rank.get(issue.severity, 0), -source_rank.get(issue.source.value, 0), issue.rule_id),
    )[:limit]


def render_summary_text(result: ReviewResult) -> str:
    counts = count_by_severity(result.issues)
    lines = [
        "审查摘要：",
        f"整体风险：{result.risk_level.value}",
        f"问题总数：{result.issue_count}",
        f"高风险：{counts['high']}",
        f"中风险：{counts['medium']}",
        f"低风险：{counts['low']}",
        f"结论：{build_overall_conclusion(result)}",
    ]

    top_risks = select_top_risks(result.issues)
    if top_risks:
        lines.append("")
        lines.append("重点风险：")
        for index, issue in enumerate(top_risks, start=1):
            lines.append(f"{index}. [{issue.severity.value}] {issue.rule_id} - {issue.title}")
    return "\n".join(lines)


def render_summary_markdown(result: ReviewResult) -> str:
    counts = count_by_severity(result.issues)
    lines = [
        "## Review Summary",
        "",
        f"- **File**: `{result.file_path}`",
        f"- **Overall Risk**: `{result.risk_level.value}`",
        f"- **Issue Count**: `{result.issue_count}`",
        f"- **High**: `{counts['high']}`",
        f"- **Medium**: `{counts['medium']}`",
        f"- **Low**: `{counts['low']}`",
        "",
        f"**Conclusion**: {build_overall_conclusion(result)}",
        "",
    ]

    top_risks = select_top_risks(result.issues)
    if top_risks:
        lines.extend(["### Top Risks", "", "| # | Severity | Rule ID | Title | Source |", "|---|---|---|---|---|"])
        for index, issue in enumerate(top_risks, start=1):
            lines.append(f"| {index} | `{issue.severity.value}` | `{issue.rule_id}` | {issue.title} | `{issue.source.value}` |")
        lines.append("")
    return "\n".join(lines)
