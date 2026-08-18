from __future__ import annotations

from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    EvaluationFailureType,
    TextToSQLEvaluation,
)


def classify_failure(
    result: TextToSQLEvaluation,
) -> tuple[EvaluationFailureType, ...]:
    """将一条Evaluation结果转换成稳定的失败类型。

    这里不猜根因。

    例如：
    metric_selection失败
    只说明Metric选择不符合Golden，
    不直接断言一定是Semantic Model或Prompt的问题。
    """

    if result.passed:
        return ()

    failures: list[
        EvaluationFailureType
    ] = []

    if (
        result.actual_behavior
        is ActualAgentBehavior.ERROR
    ):
        failures.append(
            EvaluationFailureType.ERROR
        )

        return tuple(failures)

    if not result.behavior_correct:
        failures.append(
            EvaluationFailureType.BEHAVIOR
        )

    checks = (
        (
            EvaluationFailureType.TABLE_SELECTION,
            result.table_selection_correct,
        ),
        (
            EvaluationFailureType.DIMENSION_SELECTION,
            result.dimension_selection_correct,
        ),
        (
            EvaluationFailureType.METRIC_SELECTION,
            result.metric_selection_correct,
        ),
        (
            EvaluationFailureType.FILTER_SELECTION,
            result.filter_selection_correct,
        ),
        (
            EvaluationFailureType.GROUP_BY,
            result.group_by_correct,
        ),
        (
            EvaluationFailureType.PIPELINE,
            result.pipeline_success,
        ),
        (
            EvaluationFailureType.TRUSTED_SQL,
            result.trusted_sql_expectation_met,
        ),
    )

    for failure_type, value in checks:
        if value is False:
            failures.append(
                failure_type
            )

    return tuple(failures)