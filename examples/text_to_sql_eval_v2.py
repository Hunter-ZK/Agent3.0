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

            print()
            print(
                f"run={run_index} "
                f"final="
                f"{'PASS' if result.final_pass else 'FAIL'}"
            )

            print(
                "planning:",
                result.planning_pass,
            )

            print(
                "clarification:",
                result.clarification_pass,
            )

            print(
                "sql_trust:",
                result.sql_trust_pass,
            )

            print(
                "semantic:",
                result.semantic_pass,
            )

            print(
                "system_error:",
                result.system_error,
            )

            print(
                "validation:",
                result.validation_status,
            )

            print(
                "semantic_status:",
                result.semantic_status,
            )

            print(
                "reason:",
                result.reason,
            )

            if result.validation_error:
                print(
                    "validation_error:",
                    result.validation_error,
                )

    # ========================================================
    # Aggregate
    # ========================================================

    total = len(results)

    if total == 0:
        raise RuntimeError(
            "No evaluation results."
        )

    final_passes = sum(
        result.final_pass
        for result in results
    )

    planning_passes = sum(
        result.planning_pass
        for result in results
    )

    clarification_passes = sum(
        result.clarification_pass
        for result in results
    )

    trust_passes = sum(
        result.sql_trust_pass
        for result in results
    )

    semantic_passes = sum(
        result.semantic_pass
        for result in results
    )

    system_errors = sum(
        result.system_error
        for result in results
    )

    grouped = defaultdict(list)

    for result in results:
        grouped[
            result.case_id
        ].append(
            result
        )

    stable_cases = sum(
        all(
            result.final_pass
            for result
            in case_results
        )
        for case_results
        in grouped.values()
    )

    print()
    print("=" * 78)
    print("Evaluation Summary")
    print("=" * 78)

    print(
        "runs:",
        total,
    )

    print(
        "planning_accuracy:",
        f"{planning_passes}/{total}",
        f"({planning_passes / total:.1%})",
    )

    print(
        "clarification_accuracy:",
        f"{clarification_passes}/{total}",
        f"({clarification_passes / total:.1%})",
    )

    print(
        "sql_trust_rate:",
        f"{trust_passes}/{total}",
        f"({trust_passes / total:.1%})",
    )

    print(
        "semantic_pass_rate:",
        f"{semantic_passes}/{total}",
        f"({semantic_passes / total:.1%})",
    )

    print(
        "final_success_rate:",
        f"{final_passes}/{total}",
        f"({final_passes / total:.1%})",
    )

    print(
        "system_error_rate:",
        f"{system_errors}/{total}",
        f"({system_errors / total:.1%})",
    )

    print(
        "stable_cases:",
        f"{stable_cases}/{len(grouped)}",
    )

    print()
    print("Per-case stability")

    for case_id, case_results in (
        grouped.items()
    ):
        passed = sum(
            result.final_pass
            for result
            in case_results
        )

        print(
            f"- {case_id}: "
            f"{passed}/"
            f"{len(case_results)}"
        )


if __name__ == "__main__":
    main()