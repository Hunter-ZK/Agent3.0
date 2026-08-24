from __future__ import annotations

from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class SQLReviewInput:
    """
    SQL Review Capability 的公共输入 Contract。

    注意：
    这不是 engine 内部使用的 SQLReviewRequest。
    Capability 层不会把 Metadata、Provider、Retry 等
    基础设施参数暴露给调用方。
    """

    sql: str

    def __post_init__(self) -> None:
        if not self.sql.strip():
            raise ValueError(
                "sql must not be empty."
            )

@dataclass(
    frozen=True,
    slots=True,
)
class SQLReviewIssue:
    rule_id: str
    severity: str
    message: str
    suggestion: str | None

    action: str

    # 外部便利字段，由 action 派生，
    # 不是第二事实源。
    blocking: bool

    auto_fixable: bool

@dataclass(
    frozen=True,
    slots=True,
)
class SQLReviewResult:
    """
    SQL Review Capability 的公共输出 Contract。
    """

    trace_id: str | None

    original_sql: str

    # Review 阶段实际审查的 SQL。
    reviewed_sql: str | None

    # 只有最终通过可信审查才允许存在。
    trusted_sql: str | None

    success: bool
    review_status: str

    risk_level: str | None

    issues: tuple[
        SQLReviewIssue,
        ...,
    ]

    fix_applied: bool

    route_history: tuple[
        str,
        ...,
    ]

    error_message: str | None