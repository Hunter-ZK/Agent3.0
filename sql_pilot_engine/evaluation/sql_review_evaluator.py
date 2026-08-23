from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.evaluation.sql_review_cases import (
    SQLReviewGoldenCase,
)
from sql_pilot_engine.services.sql_review_contracts import (
    SQLReviewResult,
)


@dataclass(
    frozen=True,
    slots=True,
)
class SQLReviewCaseEvaluation:
    case_id: str

    passed: bool

    failures: tuple[
        str,
        ...,
    ]

    actual_success: bool
    actual_status: str

    trusted_sql_present: bool

    issue_rule_ids: tuple[
        str,
        ...,
    ]


class SQLReviewEvaluator:
    """
    SQL Review Capability 的行为评估器。

    只依赖公共 SQLReviewResult。
    """

    def evaluate(
        self,
        *,
        case: SQLReviewGoldenCase,
        result: SQLReviewResult,
    ) -> SQLReviewCaseEvaluation:

        failures: list[str] = []

        # ====================================================
        # Success
        # ====================================================

        if (
            result.success
            != case.expected_success
        ):
            failures.append(
                "success mismatch: "
                f"expected="
                f"{case.expected_success}, "
                f"actual="
                f"{result.success}"
            )

        # ====================================================
        # Trusted SQL
        # ====================================================

        trusted_sql_present = bool(
            result.trusted_sql
            and result.trusted_sql.strip()
        )

        if (
            trusted_sql_present
            != case.expect_trusted_sql
        ):
            failures.append(
                "trusted_sql mismatch: "
                f"expected="
                f"{case.expect_trusted_sql}, "
                f"actual="
                f"{trusted_sql_present}"
            )

        # ====================================================
        # Status
        # ====================================================

        if (
            case.expected_statuses
            and result.review_status
            not in case.expected_statuses
        ):
            failures.append(
                "status mismatch: "
                f"expected one of "
                f"{case.expected_statuses}, "
                f"actual="
                f"{result.review_status}"
            )

        # ====================================================
        # Issues
        # ====================================================

        issue_rule_ids = tuple(
            issue.rule_id
            for issue in result.issues
        )

        if (
            case.expect_issues is True
            and not result.issues
        ):
            failures.append(
                "expected review issues "
                "but none were returned"
            )

        if (
            case.expect_issues is False
            and result.issues
        ):
            failures.append(
                "expected no review issues "
                "but issues were returned"
            )

        # ====================================================
        # Required Rule IDs
        # ====================================================

        for expected_rule_id in (
            case.expected_rule_ids
        ):
            if expected_rule_id not in (
                issue_rule_ids
            ):
                failures.append(
                    "missing expected rule: "
                    f"{expected_rule_id}"
                )

        # ====================================================
        # Fix
        # ====================================================

        if (
            case.expect_fix_applied
            is not None
            and result.fix_applied
            != case.expect_fix_applied
        ):
            failures.append(
                "fix_applied mismatch: "
                f"expected="
                f"{case.expect_fix_applied}, "
                f"actual="
                f"{result.fix_applied}"
            )

        # ====================================================
        # System Failure Safety
        # ====================================================

        if (
            result.review_status
            == "review_failed"
            and case.case_id
            != "review_internal_failure"
        ):
            failures.append(
                "unexpected system-level "
                "review_failed status"
            )

        return SQLReviewCaseEvaluation(
            case_id=case.case_id,
            passed=not failures,
            failures=tuple(
                failures
            ),
            actual_success=(
                result.success
            ),
            actual_status=(
                result.review_status
            ),
            trusted_sql_present=(
                trusted_sql_present
            ),
            issue_rule_ids=(
                issue_rule_ids
            ),
        )