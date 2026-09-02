from __future__ import annotations

import json

from collections import (
    Counter,
    defaultdict,
)

from pathlib import Path

from sql_pilot_engine.evaluation.text_to_sql.models import (
    TextToSQLEvalResult,
)


REPORT_SCHEMA_VERSION = "1"

EVIDENCE_RULE_IDS = (
    "METRIC_TABLE",
    "METRIC_AGGREGATION",
    "METRIC_FIXED_FILTER",
    "PARTITION_CONSTRAINT",
)


def _rate(
    passed: int,
    total: int,
) -> float:

    if total <= 0:
        return 0.0

    return passed / total


def _failure_type_text(
    result: TextToSQLEvalResult,
) -> str | None:

    failure_type = (
        result.failure_type
    )

    if failure_type is None:
        return None

    value = getattr(
        failure_type,
        "value",
        failure_type,
    )

    return str(value)


def _result_to_dict(
    result: TextToSQLEvalResult,
) -> dict[str, object]:

    return {
        "case_id": (
            result.case_id
        ),

        "run_index": (
            result.run_index
        ),

        "initial_behavior": (
            result.initial_behavior
        ),

        "clarification_pass": (
            result.clarification_pass
        ),

        "planning_pass": (
            result.planning_pass
        ),

        "schema_link_pass": (
            result.schema_link_pass
        ),

        "generation_pass": (
            result.generation_pass
        ),

        "gate_pass": (
            result.gate_pass
        ),

        "semantic_pass": (
            result.semantic_pass
        ),

        "final_pass": (
            result.final_pass
        ),

        "system_error": (
            result.system_error
        ),

        "failure_type": (
            _failure_type_text(
                result
            )
        ),

        "validation_status": (
            result.validation_status
        ),

        "semantic_status": (
            result.semantic_status
        ),

        "validation_error": (
            result.validation_error
        ),

        "linking_failure_codes": list(
            result.linking_failure_codes
        ),

        "validation_rule_ids": list(
            result.validation_rule_ids
        ),

        "evidence_rule_hits": list(
            result.evidence_rule_hits
        ),

        "generated_sql": (
            result.generated_sql
        ),

        "trusted_sql": (
            result.trusted_sql
        ),

        "reason": (
            result.reason
        ),
    }


def _build_case_summaries(
    results: tuple[
        TextToSQLEvalResult,
        ...
    ],
) -> list[
    dict[str, object]
]:

    grouped: dict[
        str,
        list[
            TextToSQLEvalResult
        ],
    ] = defaultdict(list)

    for result in results:
        grouped[
            result.case_id
        ].append(
            result
        )

    summaries: list[
        dict[str, object]
    ] = []

    for case_id in sorted(
        grouped
    ):

        case_results = sorted(
            grouped[case_id],
            key=lambda item: (
                item.run_index
            ),
        )

        runs = len(
            case_results
        )

        pass_count = sum(
            result.final_pass
            for result
            in case_results
        )

        final_values = {
            result.final_pass
            for result
            in case_results
        }

        # 所有 Run 得到同一个最终结果，
        # 不论都是 PASS 还是都是 FAIL。
        stable_outcome = (
            len(final_values) == 1
        )

        # 技术方案中的：
        #
        # 5/5 才算稳定通过。
        stable_pass = (
            pass_count == runs
        )

        failure_types = sorted(
            {
                value
                for result
                in case_results
                if (
                    (
                        value
                        := _failure_type_text(
                            result
                        )
                    )
                    is not None
                )
            }
        )

        evidence_rule_hits = sorted(
            {
                rule_id
                for result
                in case_results
                for rule_id
                in result.evidence_rule_hits
            }
        )

        summaries.append(
            {
                "case_id": (
                    case_id
                ),

                "runs": runs,

                "pass_count": (
                    pass_count
                ),

                "pass_rate": (
                    _rate(
                        pass_count,
                        runs,
                    )
                ),

                "stable_outcome": (
                    stable_outcome
                ),

                "stable_pass": (
                    stable_pass
                ),

                "failure_types": (
                    failure_types
                ),

                "evidence_rule_hits": (
                    evidence_rule_hits
                ),
            }
        )

    return summaries


def build_evaluation_report(
    *,
    results: tuple[
        TextToSQLEvalResult,
        ...
    ],
    repeat: int,
) -> dict[str, object]:

    if not results:
        raise ValueError(
            "evaluation results "
            "must not be empty"
        )

    if repeat < 1:
        raise ValueError(
            "repeat must be >= 1"
        )

    total_runs = len(
        results
    )

    case_summaries = (
        _build_case_summaries(
            results
        )
    )

    total_cases = len(
        case_summaries
    )

    clarification_passes = sum(
        result.clarification_pass
        for result
        in results
    )

    planning_passes = sum(
        result.planning_pass
        for result
        in results
    )

    schema_link_passes = sum(
        result.schema_link_pass
        for result
        in results
    )

    generation_passes = sum(
        result.generation_pass
        for result
        in results
    )

    gate_passes = sum(
        result.gate_pass
        for result
        in results
    )

    semantic_passes = sum(
        result.semantic_pass
        for result
        in results
    )
    
    compilation_attempts = sum(
        result.compilation_status
        is not None

        for result
        in results
    )

    compiled_runs = sum(
        result.compilation_status
        == "compiled"

        for result
        in results
    )
    
    compile_rate = (
        compiled_runs
        / compilation_attempts

        if compilation_attempts
        else 0.0
    )

    final_passes = sum(
        result.final_pass
        for result
        in results
    )

    system_errors = sum(
        result.system_error
        for result
        in results
    )

    stable_outcome_cases = sum(
        bool(
            item[
                "stable_outcome"
            ]
        )
        for item
        in case_summaries
    )

    stable_pass_cases = sum(
        bool(
            item[
                "stable_pass"
            ]
        )
        for item
        in case_summaries
    )

    unstable_cases = (
        total_cases
        - stable_outcome_cases
    )

    failure_counts = Counter(
        failure_type
        for result
        in results
        if (
            (
                failure_type
                := _failure_type_text(
                    result
                )
            )
            is not None
        )
    )
    
    fallback_counts = Counter(
        result
        .compilation_fallback_reason

        for result
        in results

        if (
            result
            .compilation_fallback_reason
            is not None
        )
    )

    evidence_rule_hit_counts = (
        Counter(
            rule_id
            for result
            in results
            for rule_id
            in result.evidence_rule_hits
        )
    )

    gate_false_negative_runs = (
        failure_counts[
            "gate_false_negative"
        ]
    )

    gate_false_negative_cases = sum(
        1
        for item
        in case_summaries
        if (
            "gate_false_negative"
            in item[
                "failure_types"
            ]
        )
    )

    pass_with_evidence_advisory = [
        {
            "case_id": (
                result.case_id
            ),

            "run_index": (
                result.run_index
            ),

            "evidence_rule_hits": list(
                result.evidence_rule_hits
            ),
        }
        for result
        in results
        if (
            result.final_pass
            and result.evidence_rule_hits
        )
    ]

    ordered_results = sorted(
        results,
        key=lambda item: (
            item.case_id,
            item.run_index,
        ),
    )

    return {
        "schema_version": (
            REPORT_SCHEMA_VERSION
        ),

        "evaluation": (
            "text_to_sql_v2"
        ),

        "configuration": {
            "repeat": repeat,

            "case_count": (
                total_cases
            ),

            "run_count": (
                total_runs
            ),
        },

        "summary": {
            "clarification_rate": (
                _rate(
                    clarification_passes,
                    total_runs,
                )
            ),

            "planning_rate": (
                _rate(
                    planning_passes,
                    total_runs,
                )
            ),

            "schema_link_rate": (
                _rate(
                    schema_link_passes,
                    total_runs,
                )
            ),

            "generation_rate": (
                _rate(
                    generation_passes,
                    total_runs,
                )
            ),
            
            "compilation_attempts": (
                compilation_attempts
            ),

            "compiled_runs": (
                compiled_runs
            ),

            "compile_rate": (
                compile_rate
            ),

            "gate_rate": (
                _rate(
                    gate_passes,
                    total_runs,
                )
            ),

            "semantic_rate": (
                _rate(
                    semantic_passes,
                    total_runs,
                )
            ),

            "final_success_rate": (
                _rate(
                    final_passes,
                    total_runs,
                )
            ),

            "system_error_rate": (
                _rate(
                    system_errors,
                    total_runs,
                )
            ),

            "stable_outcome_cases": (
                stable_outcome_cases
            ),

            "stable_pass_cases": (
                stable_pass_cases
            ),

            "unstable_cases": (
                unstable_cases
            ),

            "stable_pass_rate": (
                _rate(
                    stable_pass_cases,
                    total_cases,
                )
            ),

            "gate_false_negative_runs": (
                gate_false_negative_runs
            ),

            "gate_false_negative_cases": (
                gate_false_negative_cases
            ),
        },

        "quality_gates": {
            # 只报告客观条件，
            # Reporter 不擅自宣布
            # 整个 Phase 3 已通过。
            "repeat_5_or_more": (
                repeat >= 5
            ),

            "gate_false_negative_zero": (
                gate_false_negative_runs
                == 0
            ),
        },

        "failure_counts": {
            key: failure_counts[key]
            for key in sorted(
                failure_counts
            )
        },
        
        "compilation_fallback_counts": {
            key: fallback_counts[key]

            for key
            in sorted(
                fallback_counts
            )
        },

        "evidence_rule_hit_counts": {
            rule_id: (
                evidence_rule_hit_counts[
                    rule_id
                ]
            )
            for rule_id
            in EVIDENCE_RULE_IDS
        },

        "pass_with_evidence_advisory": (
            pass_with_evidence_advisory
        ),

        "cases": (
            case_summaries
        ),

        "results": [
            _result_to_dict(
                result
            )
            for result
            in ordered_results
        ],
    }


def render_markdown_report(
    report: dict[str, object],
) -> str:

    configuration = (
        report[
            "configuration"
        ]
    )

    summary = (
        report[
            "summary"
        ]
    )

    quality_gates = (
        report[
            "quality_gates"
        ]
    )

    failure_counts = (
        report[
            "failure_counts"
        ]
    )

    rule_counts = (
        report[
            "evidence_rule_hit_counts"
        ]
    )

    cases = (
        report[
            "cases"
        ]
    )

    advisory_passes = (
        report[
            "pass_with_evidence_advisory"
        ]
    )

    lines: list[str] = [
        "# Text-to-SQL Evaluation V2",
        "",
        "## Configuration",
        "",
        (
            f"- Cases: "
            f"{configuration['case_count']}"
        ),
        (
            f"- Repeat: "
            f"{configuration['repeat']}"
        ),
        (
            f"- Runs: "
            f"{configuration['run_count']}"
        ),
        "",
        "## Six-Layer Summary",
        "",
        "| Layer | Rate |",
        "| --- | ---: |",
        (
            "| Clarification | "
            f"{summary['clarification_rate']:.1%} |"
        ),
        (
            "| Planning | "
            f"{summary['planning_rate']:.1%} |"
        ),
        (
            "| Schema Link | "
            f"{summary['schema_link_rate']:.1%} |"
        ),
        (
            "| Generation | "
            f"{summary['generation_rate']:.1%} |"
        ),
        (
            "| Gate | "
            f"{summary['gate_rate']:.1%} |"
        ),
        (
            "| Semantic | "
            f"{summary['semantic_rate']:.1%} |"
        ),
        (
            "| Final | "
            f"{summary['final_success_rate']:.1%} |"
        ),
        (
            "| System Error | "
            f"{summary['system_error_rate']:.1%} |"
        ),
        "",
        "## Stability",
        "",
        (
            "- Stable outcome cases: "
            f"{summary['stable_outcome_cases']}/"
            f"{configuration['case_count']}"
        ),
        (
            "- Stable PASS cases: "
            f"{summary['stable_pass_cases']}/"
            f"{configuration['case_count']}"
        ),
        (
            "- Unstable cases: "
            f"{summary['unstable_cases']}"
        ),
        (
            "- Stable PASS rate: "
            f"{summary['stable_pass_rate']:.1%}"
        ),
        "",
        "## Redline",
        "",
        (
            "- GATE_FALSE_NEGATIVE runs: "
            f"{summary['gate_false_negative_runs']}"
        ),
        (
            "- GATE_FALSE_NEGATIVE cases: "
            f"{summary['gate_false_negative_cases']}"
        ),
        (
            "- Redline satisfied: "
            f"{quality_gates['gate_false_negative_zero']}"
        ),
        "",
        "## Failure Classification",
        "",
    ]

    if failure_counts:

        lines.extend(
            (
                "| Failure Type | Count |",
                "| --- | ---: |",
            )
        )

        for failure_type in sorted(
            failure_counts
        ):
            lines.append(
                (
                    f"| {failure_type} | "
                    f"{failure_counts[failure_type]} |"
                )
            )

    else:
        lines.append(
            "No classified failures."
        )

    lines.extend(
        (
            "",
            "## Evidence Rule Hits",
            "",
            "| Rule | Hits |",
            "| --- | ---: |",
        )
    )

    for rule_id in (
        EVIDENCE_RULE_IDS
    ):
        lines.append(
            (
                f"| {rule_id} | "
                f"{rule_counts[rule_id]} |"
            )
        )

    lines.extend(
        (
            "",
            "## Per-Case Stability",
            "",
            (
                "| Case | PASS | Runs | "
                "Stable Outcome | Stable PASS | "
                "Failure Types | Evidence Rules |"
            ),
            (
                "| --- | ---: | ---: | "
                ":---: | :---: | --- | --- |"
            ),
        )
    )

    for item in cases:

        failure_text = (
            ", ".join(
                item[
                    "failure_types"
                ]
            )
            or "-"
        )

        evidence_text = (
            ", ".join(
                item[
                    "evidence_rule_hits"
                ]
            )
            or "-"
        )

        lines.append(
            (
                f"| {item['case_id']} "
                f"| {item['pass_count']} "
                f"| {item['runs']} "
                f"| {item['stable_outcome']} "
                f"| {item['stable_pass']} "
                f"| {failure_text} "
                f"| {evidence_text} |"
            )
        )

    lines.extend(
        (
            "",
            "## PASS with Evidence Advisories",
            "",
        )
    )

    if advisory_passes:

        for item in advisory_passes:

            rules = ", ".join(
                item[
                    "evidence_rule_hits"
                ]
            )

            lines.append(
                (
                    f"- {item['case_id']} "
                    f"run={item['run_index']}: "
                    f"{rules}"
                )
            )

    else:
        lines.append(
            "None."
        )

    lines.append("")

    return "\n".join(
        lines
    )


def write_evaluation_report(
    *,
    report: dict[str, object],
    output_dir: Path,
) -> tuple[
    Path,
    Path,
]:

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_dir
        / "evaluation.json"
    )

    markdown_path = (
        output_dir
        / "evaluation.md"
    )

    json_text = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    json_path.write_text(
        json_text + "\n",
        encoding="utf-8",
    )

    markdown_path.write_text(
        render_markdown_report(
            report
        ),
        encoding="utf-8",
    )

    return (
        json_path,
        markdown_path,
    )