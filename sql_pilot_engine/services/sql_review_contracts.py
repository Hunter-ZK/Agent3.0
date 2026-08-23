from __future__ import annotations

from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class SQLReviewRequest:
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
    """
    面向 Capability 调用方的精简 Issue。

    Validation Domain 内部的 Issue 仍然保留更多
    routing / metadata / source 等内部字段。
    """

    rule_id: str
    severity: str
    message: str
    suggestion: str | None

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