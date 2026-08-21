from __future__ import annotations

from sql_pilot_engine.evaluation.failure_analysis import (
    classify_failure,
)
from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    EvaluationFailureType,
    ExpectedAgentBehavior,
    TextToSQLEvaluation,
)


def test_pass_has_no_failure_types():
    result = TextToSQLEvaluation(
        case_id="pass",

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        actual_behavior=(
            ActualAgentBehavior.ANSWER
        ),

        behavior_correct=True,

        table_selection_correct=True,
        dimension_selection_correct=True,
        metric_selection_correct=True,
        filter_selection_correct=True,
        group_by_correct=True,

        pipeline_success=True,

        trusted_sql_available=True,
        trusted_sql_expectation_met=True,

        validation_status="no_issue",
        semantic_validation_status="pass",

        passed=True,
    )

    assert (
        classify_failure(result)
        == ()
    )


def test_multiple_failures_are_classified():
    result = TextToSQLEvaluation(
        case_id="multi-failure",

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        actual_behavior=(
            ActualAgentBehavior.ANSWER
        ),

        behavior_correct=True,

        table_selection_correct=True,

        dimension_selection_correct=False,

        metric_selection_correct=False,

        filter_selection_correct=True,

        group_by_correct=False,

        pipeline_success=True,

        trusted_sql_available=True,
        trusted_sql_expectation_met=True,

        validation_status="no_issue",
        semantic_validation_status="pass",

        passed=False,
    )

    failures = classify_failure(
        result
    )

    assert failures == (
        EvaluationFailureType
        .DIMENSION_SELECTION,

        EvaluationFailureType
        .METRIC_SELECTION,

        EvaluationFailureType
        .GROUP_BY,
    )


def test_behavior_failure_is_classified():
    result = TextToSQLEvaluation(
        case_id="behavior",

        expected_behavior=(
            ExpectedAgentBehavior.CLARIFY
        ),

        actual_behavior=(
            ActualAgentBehavior.ANSWER
        ),

        behavior_correct=False,

        table_selection_correct=None,
        dimension_selection_correct=None,
        metric_selection_correct=None,
        filter_selection_correct=None,
        group_by_correct=None,

        pipeline_success=True,

        trusted_sql_available=True,
        trusted_sql_expectation_met=None,

        validation_status="no_issue",
        semantic_validation_status="pass",

        passed=False,
    )

    failures = classify_failure(
        result
    )

    assert failures == (
        EvaluationFailureType.BEHAVIOR,
    )


def test_error_returns_error_failure():
    result = TextToSQLEvaluation(
        case_id="error",

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        actual_behavior=(
            ActualAgentBehavior.ERROR
        ),

        behavior_correct=False,

        table_selection_correct=None,
        dimension_selection_correct=None,
        metric_selection_correct=None,
        filter_selection_correct=None,
        group_by_correct=None,

        pipeline_success=False,

        trusted_sql_available=False,
        trusted_sql_expectation_met=False,

        validation_status=(
            "evaluation_error"
        ),

        semantic_validation_status=None,

        passed=False,

        error_message=(
            "RuntimeError: LLM unavailable"
        ),
    )

    failures = classify_failure(
        result
    )

    assert failures == (
        EvaluationFailureType.ERROR,
    )