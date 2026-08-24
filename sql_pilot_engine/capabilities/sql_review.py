from __future__ import annotations

from collections.abc import (
    Mapping,
)
from typing import Any

from sql_pilot_engine.schemas.sql_review import (
    SQLReviewIssue,
    SQLReviewInput,
    SQLReviewResult,
)
from sql_pilot_engine.workflow.sql_agent_workflow import (
    SQLAgentWorkflow,
)


class SQLReviewCapability:
    """
    用户 SQL → Trusted SQL 的 Capability

    本 Service 不负责：

    - SQL Parse
    - SQLFacts
    - Rule
    - Metadata Validation
    - Fix
    - Re-review
    - Critic

    上述能力全部由现有 SQLAgentWorkflow 负责。
    """

    def __init__(
        self,
        workflow: SQLAgentWorkflow,
    ) -> None:
        self._workflow = workflow

    def review(
        self,
        request: SQLReviewInput,
    ) -> SQLReviewResult:
        """
        对用户提交的 SQL 进行可信审查。
        """

        try:
            workflow_result = (
                self._workflow.run(
                    request.sql,
                )
            )

        except Exception as exc:
            # 只有真正的系统异常才映射为
            # review_failed。
            return SQLReviewResult(
                trace_id=None,
                original_sql=request.sql,
                reviewed_sql=None,
                trusted_sql=None,
                success=False,
                review_status=(
                    "review_failed"
                ),
                risk_level=None,
                issues=(),
                fix_applied=False,
                route_history=(),
                error_message=str(exc),
            )

        review_response = (
            workflow_result.review_response
        )

        issues = self._map_issues(
            review_response
        )

        reviewed_sql = (
            self._extract_reviewed_sql(
                review_response
            )
        )

        fix_applied = (
            workflow_result.success
            and workflow_result.final_status
            == "fix_verified"
        )

        trusted_sql = (
            workflow_result.trusted_sql
        )

        if (
            workflow_result.success
            and not trusted_sql
        ):
            raise RuntimeError(
                "Successful SQLAgentWorkflow "
                "must provide trusted_sql."
            )

        review_status = (
            self._map_status(
                success=(
                    workflow_result.success
                ),
                final_status=(
                    workflow_result
                    .final_status
                ),
                fix_applied=(
                    fix_applied
                ),
            )
        )

        risk_level = (
            self._extract_risk_level(
                review_response
            )
        )

        return SQLReviewResult(
            trace_id=getattr(
                workflow_result,
                "trace_id",
                None,
            ),
            original_sql=request.sql,
            reviewed_sql=reviewed_sql,
            trusted_sql=trusted_sql,
            success=(
                workflow_result.success
            ),
            review_status=review_status,
            risk_level=risk_level,
            issues=issues,
            fix_applied=fix_applied,
            route_history=tuple(
                workflow_result
                .route_history
                or ()
            ),
            error_message=(
                workflow_result.error_message
                if review_status == "review_failed"
                else None
            ),
        )

    # ========================================================
    # Status Mapping
    # ========================================================

    @staticmethod
    def _map_status(
        *,
        success: bool,
        final_status: str | None,
        fix_applied: bool,
    ) -> str:
        """
        将 Workflow 内部状态转换为稳定的
        Capability Status。
        """

        if success and fix_applied:
            return "fixed"

        if success:
            return (
                final_status
                or "no_issue"
            )

        return (
            final_status
            or "review_failed"
        )

    # ========================================================
    # Issue Mapping
    # ========================================================

    def _map_issues(
        self,
        review_response: Any,
    ) -> tuple[
        SQLReviewIssue,
        ...,
    ]:
        if review_response is None:
            return ()

        raw_issues = (
            getattr(
                review_response,
                "issues",
                None,
            )
            or ()
        )

        mapped: list[
            SQLReviewIssue
        ] = []

        for issue in raw_issues:
            mapped.append(
                SQLReviewIssue(
                    rule_id=str(
                        self._read_value(
                            issue,
                            "rule_id",
                            "UNKNOWN",
                        )
                    ),
                    severity=(
                        self._to_string(
                            self._read_value(
                                issue,
                                "severity",
                                "unknown",
                            )
                        )
                    ),
                    message=str(
                        self._read_value(
                            issue,
                            "message",
                            "",
                        )
                    ),
                    suggestion=(
                        self._optional_string(
                            self._read_value(
                                issue,
                                "suggestion",
                                None,
                            )
                        )
                    ),
                    action=(
                        self._to_string(
                            self._read_value(
                                issue,
                                "action",
                                "human_review",
                            )
                        )
                    ),
                    blocking=bool(
                        self._read_value(
                            issue,
                            "blocking",
                            False,
                        )
                    ),
                    auto_fixable=bool(
                        self._read_value(
                            issue,
                            "auto_fixable",
                            False,
                        )
                    ),
                )
            )

        return tuple(
            mapped
        )

    # ========================================================
    # SQL Extraction
    # ========================================================

    @staticmethod
    def _extract_reviewed_sql(
        response: Any,
    ) -> str | None:
        if response is None:
            return None

        raw_result = getattr(
            response,
            "raw_result",
            None,
        )

        if raw_result is None:
            return None

        reviewed_sql = getattr(
            raw_result,
            "reviewed_sql",
            None,
        )

        if (
            isinstance(
                reviewed_sql,
                str,
            )
            and reviewed_sql.strip()
        ):
            return reviewed_sql

        return None


    # ========================================================
    # Fix / Risk
    # ========================================================


    def _extract_risk_level(
        self,
        review_response: Any,
    ) -> str | None:
        if review_response is None:
            return None

        value = getattr(
            review_response,
            "risk_level",
            None,
        )

        if value is None:
            return None

        return self._to_string(
            value
        )

    # ========================================================
    # Generic Helpers
    # ========================================================

    @staticmethod
    def _read_value(
        source: Any,
        key: str,
        default: Any,
    ) -> Any:
        if isinstance(
            source,
            Mapping,
        ):
            return source.get(
                key,
                default,
            )

        return getattr(
            source,
            key,
            default,
        )

    @staticmethod
    def _to_string(
        value: Any,
    ) -> str:
        enum_value = getattr(
            value,
            "value",
            None,
        )

        if enum_value is not None:
            return str(
                enum_value
            )

        return str(
            value
        )

    @staticmethod
    def _optional_string(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        return str(
            value
        )