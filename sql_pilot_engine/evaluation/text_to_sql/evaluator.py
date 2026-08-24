from __future__ import annotations

from typing import Any

from sql_pilot_engine.evaluation.text_to_sql.models import (
    TextToSQLEvalCase,
    TextToSQLEvalResult,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLRequest,
    TextToSQLResult,
)


TRUSTED_VALIDATION_STATUSES = {
    "no_issue",
    "trusted_with_advisories",
    "fix_verified",
}


def _normalize_name(
    value: str,
) -> str:
    return (
        value
        .strip()
        .lower()
        .rsplit(".", maxsplit=1)[-1]
    )


def _contains_expected(
    *,
    actual: tuple[str, ...],
    expected: tuple[str, ...],
) -> bool:

    if not expected:
        return True

    actual_values = {
        _normalize_name(item)
        for item in actual
    }

    expected_values = {
        _normalize_name(item)
        for item in expected
    }

    return (
        expected_values
        <= actual_values
    )


def _filters_match(
    response: TextToSQLResult,
    case: TextToSQLEvalCase,
) -> bool:

    if not case.required_filter_terms:
        return True

    filter_text = " ".join(
        response.query_plan.filters
    )

    normalized = (
        filter_text
        .lower()
        .replace(" ", "")
    )

    return all(
        term.lower().replace(
            " ",
            "",
        )
        in normalized
        for term
        in case.required_filter_terms
    )


def _score_planning(
    *,
    response: TextToSQLResult,
    case: TextToSQLEvalCase,
) -> tuple[bool, str]:

    plan = response.query_plan

    if not _contains_expected(
        actual=plan.tables,
        expected=case.expected_tables,
    ):
        return (
            False,
            (
                "table mismatch: "
                f"expected={case.expected_tables}, "
                f"actual={plan.tables}"
            ),
        )

    if not _contains_expected(
        actual=plan.metrics,
        expected=case.expected_metrics,
    ):
        return (
            False,
            (
                "metric mismatch: "
                f"expected={case.expected_metrics}, "
                f"actual={plan.metrics}"
            ),
        )

    if not _contains_expected(
        actual=plan.dimensions,
        expected=case.expected_dimensions,
    ):
        return (
            False,
            (
                "dimension mismatch: "
                f"expected="
                f"{case.expected_dimensions}, "
                f"actual={plan.dimensions}"
            ),
        )

    if not _contains_expected(
        actual=plan.group_by,
        expected=case.expected_group_by,
    ):
        return (
            False,
            (
                "group_by mismatch: "
                f"expected="
                f"{case.expected_group_by}, "
                f"actual={plan.group_by}"
            ),
        )

    if not _filters_match(
        response,
        case,
    ):
        return (
            False,
            (
                "required filter missing: "
                f"{case.required_filter_terms}; "
                f"actual={plan.filters}"
            ),
        )

    return (
        True,
        "planning matched",
    )


def _score_final_result(
    *,
    response: TextToSQLResult,
    case: TextToSQLEvalCase,
    clarification_pass: bool,
    initial_behavior: str,
    run_index: int,
) -> TextToSQLEvalResult:

    planning_pass, planning_reason = (
        _score_planning(
            response=response,
            case=case,
        )
    )

    validation_status = (
        response.validation_status
    )

    semantic_status = (
        response
        .semantic_validation_status
    )

    sql_trust_pass = (
        validation_status
        in TRUSTED_VALIDATION_STATUSES
    )

    semantic_pass = (
        semantic_status == "pass"
    )

    system_error = (
        validation_status
        == "review_failed"
    )

    final_pass = all(
        (
            clarification_pass,
            planning_pass,
            sql_trust_pass,
            semantic_pass,
            response.success,
            response.trusted_sql
            is not None,
            not system_error,
        )
    )

    reasons: list[str] = []

    if not planning_pass:
        reasons.append(
            planning_reason
        )

    if not sql_trust_pass:
        reasons.append(
            "SQL Trust failed: "
            f"{validation_status}"
        )

    if not semantic_pass:
        reasons.append(
            "Semantic failed: "
            f"{semantic_status}; "
            f"issues="
            f"{response.semantic_issues}"
        )

    if system_error:
        reasons.append(
            "system error: "
            f"{getattr(
                response,
                'validation_error_message',
                None,
            )}"
        )

    if (
        response.success
        and response.trusted_sql is None
    ):
        reasons.append(
            "success=True but "
            "trusted_sql is None"
        )

    if not reasons:
        reasons.append(
            "all evaluation layers passed"
        )

    return TextToSQLEvalResult(
        case_id=case.case_id,
        run_index=run_index,
        initial_behavior=(
            initial_behavior
        ),
        planning_pass=planning_pass,
        clarification_pass=(
            clarification_pass
        ),
        sql_trust_pass=(
            sql_trust_pass
        ),
        semantic_pass=(
            semantic_pass
        ),
        final_pass=final_pass,
        system_error=system_error,
        validation_status=(
            validation_status
        ),
        semantic_status=(
            semantic_status
        ),
        validation_error=getattr(
            response,
            "validation_error_message",
            None,
        ),
        generated_sql=(
            response.generated_sql
        ),
        trusted_sql=(
            response.trusted_sql
        ),
        reason="; ".join(
            reasons
        ),
    )


def evaluate_case(
    *,
    service: Any,
    case: TextToSQLEvalCase,
    run_index: int = 1,
) -> TextToSQLEvalResult:

    try:
        response = service.generate(
            TextToSQLRequest(
                question=case.question,
                dialect="maxcompute",
            )
        )

    except Exception as error:
        return TextToSQLEvalResult(
            case_id=case.case_id,
            run_index=run_index,
            initial_behavior=(
                "exception"
            ),
            planning_pass=False,
            clarification_pass=False,
            sql_trust_pass=False,
            semantic_pass=False,
            final_pass=False,
            system_error=True,
            validation_status=None,
            semantic_status=None,
            validation_error=str(error),
            generated_sql=None,
            trusted_sql=None,
            reason=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

    # ========================================================
    # Case 应当直接返回结果
    # ========================================================

    if (
        case.expected_initial
        == "result"
    ):
        if isinstance(
            response,
            TextToSQLClarification,
        ):
            return TextToSQLEvalResult(
                case_id=case.case_id,
                run_index=run_index,
                initial_behavior=(
                    "clarification"
                ),
                planning_pass=False,
                clarification_pass=False,
                sql_trust_pass=False,
                semantic_pass=False,
                final_pass=False,
                system_error=False,
                validation_status=None,
                semantic_status=None,
                validation_error=None,
                generated_sql=None,
                trusted_sql=None,
                reason=(
                    "unexpected clarification: "
                    f"{response.clarification_question}"
                ),
            )

        return _score_final_result(
            response=response,
            case=case,
            clarification_pass=True,
            initial_behavior="result",
            run_index=run_index,
        )

    # ========================================================
    # Case 应当 Clarification
    # ========================================================

    if not isinstance(
        response,
        TextToSQLClarification,
    ):
        return TextToSQLEvalResult(
            case_id=case.case_id,
            run_index=run_index,
            initial_behavior="result",
            planning_pass=False,
            clarification_pass=False,
            sql_trust_pass=False,
            semantic_pass=False,
            final_pass=False,
            system_error=False,
            validation_status=getattr(
                response,
                "validation_status",
                None,
            ),
            semantic_status=getattr(
                response,
                "semantic_validation_status",
                None,
            ),
            validation_error=getattr(
                response,
                "validation_error_message",
                None,
            ),
            generated_sql=getattr(
                response,
                "generated_sql",
                None,
            ),
            trusted_sql=getattr(
                response,
                "trusted_sql",
                None,
            ),
            reason=(
                "expected clarification "
                "but received result"
            ),
        )

    if not response.thread_id:
        return TextToSQLEvalResult(
            case_id=case.case_id,
            run_index=run_index,
            initial_behavior=(
                "clarification"
            ),
            planning_pass=False,
            clarification_pass=False,
            sql_trust_pass=False,
            semantic_pass=False,
            final_pass=False,
            system_error=True,
            validation_status=None,
            semantic_status=None,
            validation_error=(
                "clarification has no thread_id"
            ),
            generated_sql=None,
            trusted_sql=None,
            reason=(
                "clarification cannot resume"
            ),
        )

    if not case.clarification_answer:
        return TextToSQLEvalResult(
            case_id=case.case_id,
            run_index=run_index,
            initial_behavior=(
                "clarification"
            ),
            planning_pass=False,
            clarification_pass=True,
            sql_trust_pass=False,
            semantic_pass=False,
            final_pass=False,
            system_error=False,
            validation_status=None,
            semantic_status=None,
            validation_error=None,
            generated_sql=None,
            trusted_sql=None,
            reason=(
                "clarification behavior passed; "
                "no resume answer configured"
            ),
        )

    try:
        resumed = service.resume(
            thread_id=response.thread_id,
            answer=(
                case.clarification_answer
            ),
        )

    except Exception as error:
        return TextToSQLEvalResult(
            case_id=case.case_id,
            run_index=run_index,
            initial_behavior=(
                "clarification"
            ),
            planning_pass=False,
            clarification_pass=True,
            sql_trust_pass=False,
            semantic_pass=False,
            final_pass=False,
            system_error=True,
            validation_status=None,
            semantic_status=None,
            validation_error=str(error),
            generated_sql=None,
            trusted_sql=None,
            reason=(
                "resume failed: "
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

    if isinstance(
        resumed,
        TextToSQLClarification,
    ):
        return TextToSQLEvalResult(
            case_id=case.case_id,
            run_index=run_index,
            initial_behavior=(
                "clarification"
            ),
            planning_pass=False,
            clarification_pass=True,
            sql_trust_pass=False,
            semantic_pass=False,
            final_pass=False,
            system_error=False,
            validation_status=None,
            semantic_status=None,
            validation_error=None,
            generated_sql=None,
            trusted_sql=None,
            reason=(
                "clarification answer supplied "
                "but agent asked again: "
                f"{resumed.clarification_question}"
            ),
        )

    return _score_final_result(
        response=resumed,
        case=case,
        clarification_pass=True,
        initial_behavior=(
            "clarification"
        ),
        run_index=run_index,
    )