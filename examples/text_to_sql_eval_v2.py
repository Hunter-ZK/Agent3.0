from __future__ import annotations

import argparse
from collections import defaultdict

from text_to_sql_demo import (
    build_demo_service,
)

from sql_pilot_engine.evaluation.text_to_sql.cases import (
    TEXT_TO_SQL_V2_CASES,
)
from sql_pilot_engine.evaluation.text_to_sql.evaluator import (
    evaluate_case,
)

from pathlib import Path

from sql_pilot_engine.evaluation.text_to_sql.reporting import (
    build_evaluation_report,
    write_evaluation_report,
)


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Agent3.0 Text-to-SQL "
            "Evaluation V2"
        )
    )

    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help=(
            "只运行指定 case_id；"
            "可以重复指定。"
        ),
    )

    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=(
            "每个 Case 重复执行次数。"
        ),
    )

    parser.add_argument(
        "--report-dir",
        default=(
            "reports/evaluation/"
            "text_to_sql"
        ),
        help=(
            "JSON / Markdown "
            "Evaluation 报告输出目录。"
        ),
    )

    parser.add_argument(
        "--no-report",
        action="store_true",
        help=(
            "只运行 Evaluation，"
            "不写报告文件。"
        ),
    )

    return parser.parse_args()


def main() -> None:

    args = parse_args()

    if args.repeat < 1:
        raise ValueError(
            "--repeat must be >= 1"
        )

    cases = (
        TEXT_TO_SQL_V2_CASES
    )

    if args.cases:
        selected = set(
            args.cases
        )

        cases = tuple(
            case
            for case in cases
            if case.case_id in selected
        )

        unknown = (
            selected
            - {
                case.case_id
                for case
                in TEXT_TO_SQL_V2_CASES
            }
        )

        if unknown:
            raise ValueError(
                "Unknown case_id: "
                f"{sorted(unknown)}"
            )

    print("=" * 78)
    print(
        "Agent3.0 · "
        "Text-to-SQL Evaluation V2"
    )
    print("=" * 78)

    print(
        "cases:",
        len(cases),
    )

    print(
        "repeat:",
        args.repeat,
    )

    service = build_demo_service(
        use_real_llm=True
    )

    results = []

    for case in cases:

        print()
        print("#" * 78)
        print(case.case_id)
        print(case.question)
        print("#" * 78)

        for run_index in range(
            1,
            args.repeat + 1,
        ):

            result = evaluate_case(
                service=service,
                case=case,
                run_index=run_index,
            )

            results.append(
                result
            )
            
            print(
                "planning:",
                result.planning_pass,
            )

            print(
                "schema_link:",
                result.schema_link_pass,
            )

            print(
                "generation:",
                result.generation_pass,
            )

            print(
                "gate:",
                result.gate_pass,
            )

            print(
                "semantic:",
                result.semantic_pass,
            )

            print(
                "final:",
                result.final_pass,
            )

            print(
                "failure_type:",
                (
                    result.failure_type.value
                    if result.failure_type
                    else None
                ),
            )
            
            print(
                "reason:",
                result.reason,
            )

            print(
                "generation_source:",
                result.generation_source,
            )

            print(
                "compilation_status:",
                result.compilation_status,
            )

            print(
                "compilation_fallback_reason:",
                result.compilation_fallback_reason,
            )

            print(
                "evidence_rule_hits:",
                result.evidence_rule_hits,
            )

            
        report = (
            build_evaluation_report(
                results=tuple(
                    results
                ),
                repeat=args.repeat,
            )
        )
                
        summary = (
            report["summary"]
        )

        configuration = (
            report["configuration"]
        )

        print()
        print("=" * 78)
        print(
            "Evaluation Summary"
        )
        print("=" * 78)

        print(
            "runs:",
            configuration[
                "run_count"
            ],
        )

        print(
            "planning_rate:",
            f"{summary['planning_rate']:.1%}",
        )

        print(
            "schema_link_rate:",
            f"{summary['schema_link_rate']:.1%}",
        )

        print(
            "generation_rate:",
            f"{summary['generation_rate']:.1%}",
        )

        print(
            "gate_rate:",
            f"{summary['gate_rate']:.1%}",
        )

        print(
            "semantic_rate:",
            f"{summary['semantic_rate']:.1%}",
        )

        print(
            "final_success_rate:",
            f"{summary['final_success_rate']:.1%}",
        )

        print(
            "stable_pass:",
            (
                f"{summary['stable_pass_cases']}/"
                f"{configuration['case_count']}"
            ),
        )

        print(
            "unstable_cases:",
            summary[
                "unstable_cases"
            ],
        )

        print(
            "gate_false_negative:",
            summary[
                "gate_false_negative_runs"
            ],
        )


        print()
        print(
            "Evidence Rule Hits"
        )

        for (
            rule_id,
            count,
        ) in report[
            "evidence_rule_hit_counts"
        ].items():

            print(
                f"- {rule_id}: "
                f"{count}"
            )


        advisory_passes = (
            report[
                "pass_with_evidence_advisory"
            ]
        )

        print()
        print(
            "PASS with Evidence Advisories:",
            len(
                advisory_passes
            ),
        )

        for item in (
            advisory_passes
        ):
            print(
                f"- {item['case_id']} "
                f"run={item['run_index']}: "
                f"{item['evidence_rule_hits']}"
            )


        if not args.no_report:

            json_path, markdown_path = (
                write_evaluation_report(
                    report=report,

                    output_dir=Path(
                        args.report_dir
                    ),
                )
            )

            print()
            print(
                "JSON report:",
                json_path,
            )

            print(
                "Markdown report:",
                markdown_path,
            )
                        



if __name__ == "__main__":
    main()