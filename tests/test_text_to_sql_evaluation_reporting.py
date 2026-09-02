from __future__ import annotations

import json

from sql_pilot_engine.evaluation.text_to_sql.models import (
    EvaluationFailureType,
    TextToSQLEvalResult,
)

from sql_pilot_engine.evaluation.text_to_sql.reporting import (
    build_evaluation_report,
    render_markdown_report,
    write_evaluation_report,
)


def _result(
    *,
    case_id: str,
    run_index: int,
    final_pass: bool,
    failure_type: (
        EvaluationFailureType
        | None
    ) = None,
    evidence_rule_hits: tuple[
        str,
        ...
    ] = (),
    semantic_pass: bool | None = None,
) -> TextToSQLEvalResult:

    if semantic_pass is None:
        semantic_pass = (
            final_pass
        )

    return TextToSQLEvalResult(
        case_id=case_id,

        run_index=run_index,

        initial_behavior="result",

        clarification_pass=True,

        planning_pass=True,

        schema_link_pass=True,

        generation_pass=True,

        gate_pass=True,

        semantic_pass=(
            semantic_pass
        ),

        final_pass=(
            final_pass
        ),

        system_error=False,

        failure_type=(
            failure_type
        ),

        validation_status=(
            "trusted_with_advisories"
            if evidence_rule_hits
            else "no_issue"
        ),

        semantic_status=(
            "pass"
            if semantic_pass
            else "fail"
        ),

        validation_error=None,

        generated_sql=(
            "SELECT 1"
        ),

        trusted_sql=(
            "SELECT 1"
            if final_pass
            else None
        ),

        reason=(
            "test"
        ),

        linking_failure_codes=(),

        validation_rule_ids=(
            evidence_rule_hits
        ),

        evidence_rule_hits=(
            evidence_rule_hits
        ),
    )


def test_five_of_five_is_stable_pass():

    results = tuple(
        _result(
            case_id="case_a",

            run_index=index,

            final_pass=True,
        )

        for index in range(
            1,
            6,
        )
    )

    report = (
        build_evaluation_report(
            results=results,
            repeat=5,
        )
    )

    summary = (
        report["summary"]
    )

    case = (
        report["cases"][0]
    )

    assert (
        case[
            "pass_count"
        ]
        == 5
    )

    assert (
        case[
            "stable_outcome"
        ]
        is True
    )

    assert (
        case[
            "stable_pass"
        ]
        is True
    )

    assert (
        summary[
            "stable_pass_cases"
        ]
        == 1
    )


def test_consistent_failure_is_stable_but_not_pass():

    results = tuple(
        _result(
            case_id="case_a",

            run_index=index,

            final_pass=False,

            failure_type=(
                EvaluationFailureType
                .GENERATION_ERROR
            ),
        )

        for index in range(
            1,
            6,
        )
    )

    report = (
        build_evaluation_report(
            results=results,
            repeat=5,
        )
    )

    case = (
        report["cases"][0]
    )

    assert (
        case[
            "stable_outcome"
        ]
        is True
    )

    assert (
        case[
            "stable_pass"
        ]
        is False
    )


def test_mixed_results_are_unstable():

    results = (
        _result(
            case_id="case_a",
            run_index=1,
            final_pass=True,
        ),

        _result(
            case_id="case_a",
            run_index=2,
            final_pass=False,
            failure_type=(
                EvaluationFailureType
                .GENERATION_ERROR
            ),
        ),
    )

    report = (
        build_evaluation_report(
            results=results,
            repeat=2,
        )
    )

    summary = (
        report["summary"]
    )

    case = (
        report["cases"][0]
    )

    assert (
        case[
            "stable_outcome"
        ]
        is False
    )

    assert (
        summary[
            "unstable_cases"
        ]
        == 1
    )


def test_gate_false_negative_is_report_redline():

    results = (
        _result(
            case_id="case_a",

            run_index=1,

            final_pass=False,

            semantic_pass=False,

            failure_type=(
                EvaluationFailureType
                .GATE_FALSE_NEGATIVE
            ),
        ),
    )

    report = (
        build_evaluation_report(
            results=results,
            repeat=1,
        )
    )

    summary = (
        report["summary"]
    )

    quality = (
        report[
            "quality_gates"
        ]
    )

    assert (
        summary[
            "gate_false_negative_runs"
        ]
        == 1
    )

    assert (
        summary[
            "gate_false_negative_cases"
        ]
        == 1
    )

    assert (
        quality[
            "gate_false_negative_zero"
        ]
        is False
    )


def test_evidence_advisory_is_visible_in_report():

    results = (
        _result(
            case_id="case_a",

            run_index=1,

            final_pass=True,

            evidence_rule_hits=(
                "METRIC_AGGREGATION",
            ),
        ),
    )

    report = (
        build_evaluation_report(
            results=results,
            repeat=1,
        )
    )

    assert (
        report[
            "evidence_rule_hit_counts"
        ][
            "METRIC_AGGREGATION"
        ]
        == 1
    )

    advisory_passes = (
        report[
            "pass_with_evidence_advisory"
        ]
    )

    assert (
        len(
            advisory_passes
        )
        == 1
    )

    assert (
        advisory_passes[0][
            "case_id"
        ]
        == "case_a"
    )


def test_report_output_is_deterministic(
    tmp_path,
):

    results = (
        _result(
            case_id="case_b",
            run_index=1,
            final_pass=True,
        ),

        _result(
            case_id="case_a",
            run_index=1,
            final_pass=True,
        ),
    )

    report = (
        build_evaluation_report(
            results=results,
            repeat=1,
        )
    )

    first_json, first_md = (
        write_evaluation_report(
            report=report,

            output_dir=(
                tmp_path
                / "first"
            ),
        )
    )

    second_json, second_md = (
        write_evaluation_report(
            report=report,

            output_dir=(
                tmp_path
                / "second"
            ),
        )
    )

    assert (
        first_json.read_text(
            encoding="utf-8"
        )
        == second_json.read_text(
            encoding="utf-8"
        )
    )

    assert (
        first_md.read_text(
            encoding="utf-8"
        )
        == second_md.read_text(
            encoding="utf-8"
        )
    )

    payload = json.loads(
        first_json.read_text(
            encoding="utf-8"
        )
    )

    assert (
        payload[
            "cases"
        ][0][
            "case_id"
        ]
        == "case_a"
    )

    markdown = (
        render_markdown_report(
            report
        )
    )

    assert (
        "GATE_FALSE_NEGATIVE"
        in markdown
    )

    assert (
        "Per-Case Stability"
        in markdown
    )