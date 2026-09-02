"""
Trusted SQL 与 SQL Review 共享的核心枚举。

【架构位置】
Deterministic Rule / Metadata Validator / LLM Reviewer
    -> Issue(severity, source, action)
    -> Review Routing / TrustedSQLWorkflow

【设计原则】
Severity 只描述风险强度；IssueAction 才是 Workflow 路由的唯一事实源。
因此 HIGH 并不自动等于 BLOCK，LLM 产生的高风险意见也不能绕过确定性证据直接阻断 SQL。

本模块只定义稳定枚举语义，不包含任何具体规则判断。
"""

from enum import Enum


class Severity(str, Enum):
    """
    Issue 的风险等级，用于展示、排序与报告。

    注意：severity 不决定 SQL 是否可进入 Trusted SQL 生命周期；真正的路由依据是 IssueAction。
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IssueSource(str, Enum):
    """Issue 的事实来源，帮助审计系统区分确定性规则、LLM 判断和系统异常。"""

    # 由确定性 Rule / Validator 产生，可在证据充分时形成权威阻断。
    RULE = "rule"

    # 由 LLM Reviewer 产生。LLM opinion 本身不是 Deterministic Evidence。
    LLM = "llm"

    # 由系统基础设施、解析或内部 Contract 异常产生。
    SYSTEM = "system"


class IssueAction(str, Enum):
    """
    Issue 对 Trusted SQL 生命周期的处理动作，也是 Review Routing 的唯一事实源。

    语义约束：
    - BLOCK：确定性证据已经证明硬性违规；
    - AUTO_FIX：存在唯一且安全的自动修复；
    - CONTEXT_REQUIRED：只有用户/业务上下文能补齐缺失事实；
    - HUMAN_REVIEW：当前证据不足以安全自动决策；
    - ADVISORY：有价值但不阻断；
    - IGNORE：内部噪声，不进入用户侧结果。
    """

    AUTO_FIX = "auto_fix"
    CONTEXT_REQUIRED = "context_required"
    HUMAN_REVIEW = "human_review"
    BLOCK = "block"
    ADVISORY = "advisory"
    IGNORE = "ignore"


class FixType(str, Enum):
    """修复建议的执行方式，用于区分自动补丁、人工指导和纯诊断信息。"""

    AUTO_PATCH = "auto_patch"
    MANUAL_GUIDANCE = "manual_guidance"
    DIAGNOSTIC = "diagnostic"
