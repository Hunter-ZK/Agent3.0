from __future__ import annotations

import argparse
from pathlib import Path

from text_to_sql_demo import build_demo_service

from sql_pilot_engine.evaluation.text_to_sql.cases import TEXT_TO_SQL_V2_CASES
from sql_pilot_engine.evaluation.text_to_sql.evaluator import evaluate_case
from sql_pilot_engine.evaluation.text_to_sql.reporting import (
    build_evaluation_report,
    write_evaluation_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent3.0 Text-to-SQL Evaluation V2"
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="只运行指定 case_id；可以重复指定。",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="每个 Case 重复执行次数。",
    )
    parser.add_argument(
        "--report-dir",
        default="reports/evaluation/text_to_sql",
        help="JSON / Markdown Evaluation 报告输出目录。",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="只运行 Evaluation，不写报告文件。",
    )
    parser.add_argument(
        "--use-real-llm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "是否使用真实 LLM。正式质量评测应保持开启；"
            "--no-use-real-llm 只用于离线管线冒烟，不代表模型准确率。"
        ),
    )
    return parser.parse_args()


def _select_cases(case_ids: list[str] | None):
    if not case_ids:
        return TEXT_TO_SQL_V2_CASES

    selected = set(case_ids)
    known = {
        case.case_id
        for case in TEXT_TO_SQL_V2_CASES
    }
    unknown = selected - known
    if unknown:
        raise ValueError(
            f"Unknown case_id: {sorted(unknown)}"
        )

    return tuple(
        case
        for case in TEXT_TO_SQL_V2_CASES
        if case.case_id in selected
    )


def _print_run_result(result) -> None:
    print("planning:", result.planning_pass)
    print("schema_link:", result.schema_link_pass)
    print("generation:", result.generation_pass)
    print("gate:", result.gate_pass)
    print("semantic:", result.semantic_pass)
    print("final:", result.final_pass)
    print(
        "failure_type:",
        result.failure_type.value
        if result.failure_type
        else None,
    )
    print("reason:", result.reason)
    print("generation_source:", result.generation_source)
    print("compilation_status:", result.compilation_status)
    print(
        "compilation_fallback_reason:",
        result.compilation_fallback_reason,
    )
    print("evidence_rule_hits:", result.evidence_rule_hits)


def _print_summary(report: dict) -> None:
    summary = report["summary"]
    configuration = report["configuration"]

    print()
    print("=" * 78)
    print("Evaluation Summary")
    print("=" * 78)
    print("runs:", configuration["run_count"])
    print("planning_rate:", f"{summary['planning_rate']:.1%}")
    print("schema_link_rate:", f"{summary['schema_link_rate']:.1%}")
    print("generation_rate:", f"{summary['generation_rate']:.1%}")
    print("gate_rate:", f"{summary['gate_rate']:.1%}")
    print("semantic_rate:", f"{summary['semantic_rate']:.1%}")
    print(
        "final_success_rate:",
        f"{summary['final_success_rate']:.1%}",
    )
    print(
        "stable_pass:",
        f"{summary['stable_pass_cases']}/{configuration['case_count']}",
    )
    print("unstable_cases:", summary["unstable_cases"])
    print(
        "gate_false_negative:",
        summary["gate_false_negative_runs"],
    )
    print("system_error_rate:", f"{summary['system_error_rate']:.1%}")

    print("\nEvidence Rule Hits")
    for rule_id, count in report["evidence_rule_hit_counts"].items():
        print(f"- {rule_id}: {count}")

    advisory_passes = report["pass_with_evidence_advisory"]
    print("\nPASS with Evidence Advisories:", len(advisory_passes))
    for item in advisory_passes:
        print(
            f"- {item['case_id']} run={item['run_index']}: "
            f"{item['evidence_rule_hits']}"
        )


def main() -> None:
    args = parse_args()

    if args.repeat < 1:
        raise ValueError("--repeat must be >= 1")

    cases = _select_cases(args.cases)

    print("=" * 78)
    print("Agent3.0 · Text-to-SQL Evaluation V2")
    print("=" * 78)
    print("cases:", len(cases))
    print("repeat:", args.repeat)
    print(
        "mode:",
        "real_llm_quality"
        if args.use_real_llm
        else "offline_pipeline_smoke",
    )

    if not args.use_real_llm:
        print(
            "WARNING: offline mode uses deterministic demo models and is not "
            "a Text-to-SQL accuracy measurement."
        )

    service = build_demo_service(
        use_real_llm=args.use_real_llm
    )

    results = []

    for case in cases:
        print()
        print("#" * 78)
        print(case.case_id)
        print(case.question)
        print("#" * 78)

        for run_index in range(1, args.repeat + 1):
            result = evaluate_case(
                service=service,
                case=case,
                run_index=run_index,
            )
            results.append(result)
            _print_run_result(result)

    report = build_evaluation_report(
        results=tuple(results),
        repeat=args.repeat,
    )
    _print_summary(report)

    if not args.no_report:
        json_path, markdown_path = write_evaluation_report(
            report=report,
            output_dir=Path(args.report_dir),
        )
        print("\nJSON report:", json_path)
        print("Markdown report:", markdown_path)


if __name__ == "__main__":
    main()
