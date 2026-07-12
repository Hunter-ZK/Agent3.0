# sql_review_agent/core/enums.py

from enum import Enum


class Severity(str, Enum):
    """Issue 风险等级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IssueSource(str, Enum):
    """Issue 来源。"""

    RULE = "rule"
    LLM = "llm"
    SYSTEM = "system"


class FixType(str, Enum):
    """修复建议类型。"""

    AUTO_PATCH = "auto_patch"
    MANUAL_GUIDANCE = "manual_guidance"
    DIAGNOSTIC = "diagnostic"
