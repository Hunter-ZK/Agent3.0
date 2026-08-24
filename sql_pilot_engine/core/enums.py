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

class IssueAction(str, Enum):
    """Issue 对 Trusted SQL 生命周期的处理建议。"""

    AUTO_FIX = "auto_fix"

    # 当前信息不足，需要补充 Context 后才能继续。
    CONTEXT_REQUIRED = "context_required"

    # 问题具有实质风险，但当前系统不能安全自动处理。
    HUMAN_REVIEW = "human_review"

    # 确定性安全阻断。
    BLOCK = "block"

    # Issue 有价值，需要展示，但不阻止 SQL 成为 Trusted SQL。
    ADVISORY = "advisory"

    # 完全忽略，不参与用户侧结果。
    IGNORE = "ignore"
    
    

class FixType(str, Enum):
    """修复建议类型。"""

    AUTO_PATCH = "auto_patch"
    MANUAL_GUIDANCE = "manual_guidance"
    DIAGNOSTIC = "diagnostic"
