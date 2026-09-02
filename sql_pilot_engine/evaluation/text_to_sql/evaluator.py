from __future__ import annotations

from typing import Any

from sql_pilot_engine.evaluation.text_to_sql.models import (
    TextToSQLEvalCase,
    TextToSQLEvalResult,
    EvaluationFailureType,
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

EVIDENCE_RULE_IDS = frozenset(
    {
        "METRIC_TABLE",
        "METRIC_AGGREGATION",
        "METRIC_FIXED_FILTER",
        "PARTITION_CONSTRAINT",
    }
)


def _normalize_name(
    value: str,
) -> str:
    return (
        value
        .strip()
        .lower()
        .rsplit(".", maxsplit=1)[-1]
    )

def _failure_code_text(
    failure,
) -> str:

    code = getattr(
        failure,
        "code",
        None,
    )

    if code is None:
        return ""

    value = getattr(
        code,
        "value",
        code,
    )

    return str(
        value
    ).strip().lower()
    

def _linking_failure_codes(
    response: TextToSQLResult,
) -> tuple[str, ...]:

    values: list[str] = []

    for failure in (
        getattr(
            response,
            "linking_failures",
            (),
        )
        or ()
    ):

        code = (
            _failure_code_text(
                failure
            )
        )

        if (
            code
            and code not in values
        ):
            values.append(
                code
            )

    return tuple(values)

def _validation_rule_ids(
    response: TextToSQLResult,
) -> tuple[str, ...]:

    result: list[str] = []

    for issue in (
        response.validation_issues
    ):

        rule_id = (
            issue.rule_id
            .strip()
        )

        if (
            rule_id
            and rule_id
            not in result
        ):
            result.append(
                rule_id
            )

    return tuple(result)


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

    linking_codes = (
        _linking_failure_codes(
            response
        )
    )

    schema_link_pass = (
        not linking_codes
    )

    generated_sql = (
        response.generated_sql
    )

    generation_pass = bool(
        generated_sql
        and generated_sql.strip()
    )

    validation_status = (
        response.validation_status
    )

    gate_pass = (
        validation_status
        in TRUSTED_VALIDATION_STATUSES
    )

    semantic_status = (
        response
        .semantic_validation_status
    )

    semantic_pass = (
        semantic_status
        == "pass"
    )

    validation_rule_ids = (
        _validation_rule_ids(
            response
        )
    )

    evidence_rule_hits = tuple(
        rule_id
        for rule_id
        in validation_rule_ids
        if rule_id
        in EVIDENCE_RULE_IDS
    )

    system_error = (
        validation_status
        == "review_failed"
        or "metadata_error"
        in linking_codes
    )

    final_pass = all(
        (
            clarification_pass,
            planning_pass,
            schema_link_pass,
            generation_pass,
            gate_pass,
            semantic_pass,
            response.success,
            response.trusted_sql
            is not None,
            not system_error,
        )
    )
    
    failure_type = (
        _classify_failure(
            final_pass=final_pass,

            planning_pass=(
                planning_pass
            ),

            schema_link_pass=(
                schema_link_pass
            ),

            generation_pass=(
                generation_pass
            ),

            gate_pass=gate_pass,

            semantic_pass=(
                semantic_pass
            ),

            system_error=(
                system_error
            ),

            linking_failure_codes=(
                linking_codes
            ),
        )
    )

    reasons: list[str] = []

    if not planning_pass:
        reasons.append(
            planning_reason
        )

    if not response.trusted_sql:
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

        clarification_pass=(
            clarification_pass
        ),

        planning_pass=(
            planning_pass
        ),

        schema_link_pass=(
            schema_link_pass
        ),

        generation_pass=(
            generation_pass
        ),

        gate_pass=gate_pass,

        semantic_pass=(
            semantic_pass
        ),

        final_pass=final_pass,

        system_error=(
            system_error
        ),

        failure_type=(
            failure_type
        ),

        validation_status=(
            validation_status
        ),

        semantic_status=(
            semantic_status
        ),

        validation_error=(
            response
            .validation_error_message
        ),

        generated_sql=(
            response.generated_sql
        ),

        generation_source=(
            response.generation_source
        ),

        compilation_status=(
            response.compilation_status
        ),

        compilation_fallback_reason=(
            response
            .compilation_fallback_reason
        ),

        trusted_sql=(
            response.trusted_sql
        ),

        reason="; ".join(
            reasons
        ),

        linking_failure_codes=(
            linking_codes
        ),

        validation_rule_ids=(
            validation_rule_ids
        ),

        evidence_rule_hits=(
            evidence_rule_hits
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
            generation_source=None,
            compilation_status=None,
            compilation_fallback_reason=None,
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
    
def _classify_failure(
    *,
    final_pass: bool,
    planning_pass: bool,
    schema_link_pass: bool,
    generation_pass: bool,
    gate_pass: bool,
    semantic_pass: bool,
    system_error: bool,
    linking_failure_codes: tuple[
        str,
        ...
    ],
) -> (
    EvaluationFailureType
    | None
):

    if final_pass:
        return None

    if system_error:
        return (
            EvaluationFailureType
            .SYSTEM_ERROR
        )

    # UNKNOWN_METRIC
    # 本质是 Planner 产出了
    # 当前系统不存在的逻辑 Metric。
    if (
        "unknown_metric"
        in linking_failure_codes
    ):
        return (
            EvaluationFailureType
            .PLANNING_ERROR
        )

    # 原技术方案保留此类型。
    # 你当前已经不做 Asset
    # Accuracy 主动盘点，因此只有
    # 系统明确产出这个 Failure Code
    # 时才归 Asset Defect。
    if (
        "asset_column_missing"
        in linking_failure_codes
    ):
        return (
            EvaluationFailureType
            .ASSET_DEFECT
        )

    if not planning_pass:
        return (
            EvaluationFailureType
            .PLANNING_ERROR
        )

    if not schema_link_pass:
        return (
            EvaluationFailureType
            .LINKING_ERROR
        )

    if not generation_pass:
        return (
            EvaluationFailureType
            .GENERATION_ERROR
        )

    # Gate 拒绝了一个在前面阶段
    # 已经正常生成的 Candidate。
    #
    # 仅凭当前自动证据无法证明
    # SQL 实际正确，所以此时首先
    # 归 GENERATION_ERROR：
    # Candidate 没通过 Trust Gate。
    #
    # 若人工复核确认 Candidate 实际
    # 正确，再重分类为
    # GATE_FALSE_POSITIVE。
    if not gate_pass:
        return (
            EvaluationFailureType
            .GENERATION_ERROR
        )

    # 这是最重要的红线：
    #
    # Gate 已经放行为 Candidate Trusted SQL，
    # 但后置 Semantic Validator
    # 仍判断 SQL 语义错误。
    if not semantic_pass:
        return (
            EvaluationFailureType
            .GATE_FALSE_NEGATIVE
        )

    return (
        EvaluationFailureType
        .SYSTEM_ERROR
    )