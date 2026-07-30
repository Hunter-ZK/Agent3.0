# sql_review_agent/reporting/renderers.py

import json

from sql_pilot_engine.core.models import ReviewResult
from sql_pilot_engine.reporting.summary import render_summary_markdown, render_summary_text


def render_json(result: ReviewResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def render_text(result: ReviewResult) -> str:
    result_dict = result.to_dict()
    lines: list[str] = [render_summary_text(result), ""]

    if result_dict["issue_count"] == 0:
        lines.append("未发现明显问题。")
    else:
        lines.append("问题列表：")
        for index, issue in enumerate(result_dict["issues"], start=1):
            lines.append(f"{index}. [{issue['severity']}] {issue['title']}")
            lines.append(f"   规则ID：{issue['rule_id']}")
            lines.append(f"   分类：{issue['category']}")
            lines.append(f"   来源：{issue['source']}")
            lines.append(f"   置信度：{issue['confidence']}")
            lines.append(f"   说明：{issue['message']}")
            lines.append(f"   建议：{issue['suggestion']}")
            lines.append(f"   证据：{issue['evidence']}")
            lines.append("")

    fixed_sql_result = result_dict.get("fixed_sql_result")
    if fixed_sql_result:
        lines.append("完整修复后 SQL：")
        lines.append(f"来源：{fixed_sql_result['source']}")
        if fixed_sql_result.get("applied_fixes"):
            lines.append("已应用修复：")
            for item in fixed_sql_result["applied_fixes"]:
                lines.append(f"- {item}")
        if fixed_sql_result.get("manual_notes"):
            lines.append("人工确认事项：")
            for item in fixed_sql_result["manual_notes"]:
                lines.append(f"- {item}")
        lines.append("")
        lines.append(fixed_sql_result["fixed_sql"])

    return "\n".join(lines)


def render_markdown(result: ReviewResult) -> str:
    result_dict = result.to_dict()
    lines: list[str] = ["# SQL Review Report", "", render_summary_markdown(result), "---", "", "## Issue Details", ""]

    if result_dict["issue_count"] == 0:
        lines.append("未发现明显问题。")
    else:
        for index, issue in enumerate(result_dict["issues"], start=1):
            lines.append(f"### {index}. {issue['title']}")
            lines.append("")
            lines.append(f"- **Rule ID**: `{issue['rule_id']}`")
            lines.append(f"- **Severity**: `{issue['severity']}`")
            lines.append(f"- **Category**: `{issue['category']}`")
            lines.append(f"- **Source**: `{issue['source']}`")
            lines.append(f"- **Confidence**: `{issue['confidence']}`")
            lines.append("")
            lines.append("**Message**")
            lines.append("")
            lines.append(issue["message"])
            lines.append("")
            lines.append("**Suggestion**")
            lines.append("")
            lines.append(issue["suggestion"])
            lines.append("")
            lines.append("**Evidence**")
            lines.append("")
            lines.append("```text")
            lines.append(issue["evidence"])
            lines.append("```")
            lines.append("")

    fixed_sql_result = result_dict.get("fixed_sql_result")
    if fixed_sql_result:
        lines.extend(["---", "", "## Unified Fixed SQL", "", f"- **Source**: `{fixed_sql_result['source']}`", ""])
        if fixed_sql_result.get("applied_fixes"):
            lines.extend(["### Applied Fixes", ""])
            for item in fixed_sql_result["applied_fixes"]:
                lines.append(f"- {item}")
            lines.append("")
        if fixed_sql_result.get("manual_notes"):
            lines.extend(["### Manual Review Notes", ""])
            for item in fixed_sql_result["manual_notes"]:
                lines.append(f"- {item}")
            lines.append("")
        lines.extend(["### Fixed SQL", "", "```sql", fixed_sql_result["fixed_sql"].rstrip(), "```", ""])

    return "\n".join(lines)
