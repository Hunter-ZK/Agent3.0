from __future__ import annotations

import argparse
from pathlib import Path

from sql_pilot_engine.app.text_to_sql_factory import (
    build_text_to_sql_service,
)
from sql_pilot_engine.context.semantic.loan_domain import (
    LOAN_DOMAIN_CONTEXT_DOCUMENTS,
)
from sql_pilot_engine.evaluation.golden_cases import (
    TEXT_TO_SQL_GOLDEN_V0_1,
)
from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
)
from sql_pilot_engine.evaluation.runner import (
    TextToSQLEvaluationRunner,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
)
from sql_pilot_engine.llm.deepseek_client import (
    DeepSeekLLMClient,
)
from sql_pilot_engine.observability.logging import (
    configure_logging,
)
from sql_pilot_engine.evaluation.failure_analysis import (
    classify_failure,
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Agent3.0 Text-to-SQL "
            "Evaluation V0.1"
        )
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=(
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ),
        help=(
            "日志级别，默认INFO"
        ),
    )

    return parser.parse_args()


def build_evaluation_service():
    """构建Evaluation使用的真实LLM服务。"""

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    semantic_model_path = (
        project_root
        / "sql_pilot_engine"
        / "context"
        / "semantic"
        / "loan_model.json"
    )

    model = (
        DeepSeekLLMClient.from_env()
    )

    return build_text_to_sql_service(
        semantic_model_path=(
            semantic_model_path
        ),

        context_documents=(
            LOAN_DOMAIN_CONTEXT_DOCUMENTS
        ),

        planner_model=model,

        sql_model=model,

        semantic_validator_model=model,

        collection_name=(
            "text_to_sql_evaluation"
        ),

        max_sql_retries=0,

        max_semantic_retries=1,
    )


def format_rate(
    value: float,
) -> str:
    return f"{value * 100:.1f}%"



def print_case_results(
    report,
) -> None:
    print()
    print(
        "=" * 72
    )

    print(
        "Case Results"
    )

    print(
        "=" * 72
    )
    
    case_map = {
        case.case_id: case
        for case
        in TEXT_TO_SQL_GOLDEN_V0_1
    }


    for result in report.results:
        
        case = case_map[result.case_id]
        
        marker = (
            "PASS"
            if result.passed
            else "FAIL"
        )

        print()
        print(
            f"[{marker}] "
            f"{result.case_id}"
        )

        print(
            "  expected behavior:",
            result.expected_behavior.value,
        )

        print(
            "  actual behavior:",
            result.actual_behavior.value,
        )
        
        failure_types = (
            classify_failure(
                result
            )
        )
        
        if failure_types:
            print(
                "  failure types:",
                ", ".join(
                    item.value
                    for item
                    in failure_types
                ),
            )

        # ====================================================
        # Clarification
        # ====================================================

        if result.clarification_question:
            print(
                "  clarification:",
                result.clarification_question,
            )

        # ====================================================
        # Plan Trace
        # ====================================================

        if (
            result.actual_behavior
            is ActualAgentBehavior.ANSWER
        ):
            print(
                "  plan:"
            )

            print(
                "    tables:"
            )

            print(
                "      expected:",
                case.expected_tables,
            )

            print(
                "      actual:  ",
                result.actual_tables,
            )

            print(
                "    dimensions:"
            )

            print(
                "      expected:",
                case.expected_dimensions,
            )

            print(
                "      actual:  ",
                result.actual_dimensions,
            )

            print(
                "    metrics:"
            )

            print(
                "      expected:",
                case.expected_metrics,
            )

            print(
                "      actual:  ",
                result.actual_metrics,
            )

            print(
                "    filters:"
            )

            print(
                "      expected:",
                case.expected_filters,
            )

            print(
                "      actual:  ",
                result.actual_filters,
            )

            print(
                "    group_by:"
            )

            print(
                "      expected:",
                case.expected_group_by,
            )

            print(
                "      actual:  ",
                result.actual_group_by,
            )

            print(
                "  validation:"
            )

            print(
                "    sql:",
                result.validation_status,
            )

            print(
                "    semantic:",
                (
                    result
                    .semantic_validation_status
                ),
            )

            print(
                "    pipeline_success:",
                result.pipeline_success,
            )

            print(
                "    trusted_sql:",
                result.trusted_sql_available,
            )

        if result.error_message:
            print(
                "  error:",
                result.error_message,
            )


def print_summary(
    report,
) -> None:
    summary = report.summary

    print()
    print(
        "=" * 72
    )

    print(
        "Agent3.0 · Text-to-SQL "
        "Evaluation V0.1"
    )

    print(
        "=" * 72
    )

    print()
    print(
        "Cases:",
        summary.total_cases,
    )

    print(
        "ANSWER cases:",
        summary.answer_cases,
    )

    print(
        "CLARIFY cases:",
        summary.clarification_cases,
    )

    print(
        "ERROR cases:",
        summary.error_cases,
    )

    print()
    print(
        "Overall Pass Rate:",
        format_rate(
            summary.pass_rate
        ),
    )

    print(
        "Behavior Accuracy:",
        format_rate(
            summary.behavior_accuracy
        ),
    )

    print(
        "Error Rate:",
        format_rate(
            summary.error_rate
        ),
    )

    print()
    print(
        "Table Accuracy:",
        format_rate(
            summary
            .table_selection_accuracy
        ),
    )

    print(
        "Dimension Accuracy:",
        format_rate(
            summary
            .dimension_selection_accuracy
        ),
    )

    print(
        "Metric Accuracy:",
        format_rate(
            summary
            .metric_selection_accuracy
        ),
    )

    print(
        "Filter Accuracy:",
        format_rate(
            summary
            .filter_selection_accuracy
        ),
    )

    print(
        "GroupBy Accuracy:",
        format_rate(
            summary.group_by_accuracy
        ),
    )

    print()
    print(
        "Pipeline Success Rate:",
        format_rate(
            summary.pipeline_success_rate
        ),
    )

    print(
        "Trusted SQL Rate:",
        format_rate(
            summary.trusted_sql_rate
        ),
    )


def print_failure_distribution(
    report,
) -> None:

    counts: dict[str, int] = {}

    for result in report.results:
        for failure_type in (
            classify_failure(
                result
            )
        ):
            key = failure_type.value

            counts[key] = (
                counts.get(
                    key,
                    0,
                )
                + 1
            )

    print()
    print("=" * 72)
    print("Failure Distribution")
    print("=" * 72)

    if not counts:
        print(
            "No failures."
        )
        return

    for name, count in sorted(
        counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"{name}: {count}"
        )


def main() -> None:
    args = parse_args()

    configure_logging(
        args.log_level
    )

    service = (
        build_evaluation_service()
    )

    evaluator = (
        TextToSQLEvaluator()
    )

    runner = (
        TextToSQLEvaluationRunner(
            service=service,
            evaluator=evaluator,
        )
    )

    report = runner.run(
        TEXT_TO_SQL_GOLDEN_V0_1
    )

    print_summary(
        report
    )

    print_failure_distribution(
        report
    )

    print_case_results(
        report
    )

    print()


if __name__ == "__main__":
    main()