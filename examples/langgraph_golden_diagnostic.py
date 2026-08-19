from __future__ import annotations

from uuid import uuid4

from langgraph_text_to_sql_demo import (
    build_graph,
)

from sql_pilot_engine.evaluation.golden_cases import (
    TEXT_TO_SQL_GOLDEN_V0_1,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLResponse,
    TextToSQLResult,
)


# 目前只诊断这三个失败Case。
TARGET_CASE_IDS = {
    case.case_id
    for case
    in TEXT_TO_SQL_GOLDEN_V0_1
}


def status_text(
    value,
) -> str:
    if value is None:
        return "None"

    enum_value = getattr(
        value,
        "value",
        None,
    )

    if enum_value is not None:
        return str(enum_value)

    return str(value)


def state_to_response(
    *,
    question: str,
    state: dict,
) -> TextToSQLResponse:
    """
    仅用于Evaluation诊断：
    把LangGraph内部State转换成现有公共Response DTO。
    """

    interrupts = state.get(
        "__interrupt__"
    )

    if interrupts:
        payload = getattr(
            interrupts[0],
            "value",
            {},
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise RuntimeError(
                "Invalid interrupt payload."
            )

        return TextToSQLClarification(
            question=question,

            clarification_question=str(
                payload.get(
                    "question",
                    "",
                )
                or ""
            ),

            missing_context=tuple(
                payload.get(
                    "missing_context",
                    (),
                )
                or ()
            ),

            reason=str(
                payload.get(
                    "reason",
                    "",
                )
                or ""
            ),
        )

    query_plan = state.get(
        "query_plan"
    )

    if query_plan is None:
        raise RuntimeError(
            "Graph finished without "
            "query_plan or clarification."
        )

    semantic_result = state.get(
        "semantic_result"
    )

    semantic_status = state.get(
        "semantic_validation_status"
    )

    return TextToSQLResult(
        question=question,

        query_plan=query_plan,

        generated_sql=str(
            state.get(
                "generated_sql",
                "",
            )
            or ""
        ),

        trusted_sql=state.get(
            "trusted_sql"
        ),

        success=bool(
            state.get(
                "success",
                False,
            )
        ),

        validation_status=status_text(
            state.get(
                "validation_status"
            )
        ),

        semantic_validation_status=(
            None
            if semantic_status is None
            else status_text(
                semantic_status
            )
        ),

        semantic_missing_requirements=tuple(
            getattr(
                semantic_result,
                "missing_requirements",
                (),
            )
        ),

        semantic_issues=tuple(
            getattr(
                semantic_result,
                "issues",
                (),
            )
        ),
    )


def print_retrieval(
    state: dict,
) -> None:
    """
    打印Planner真正拿到的RAG Context。
    用来判断是否存在：
    - 召回错误
    - 绿色贷款知识缺失
    - Verified SQL干扰
    """

    query_context = state.get(
        "query_context"
    )

    if query_context is None:
        print(
            "\n[Retrieved Context]"
        )
        print("None")
        return

    print(
        "\n[Business Knowledge]"
    )

    if not query_context.business_knowledge:
        print("None")

    for index, item in enumerate(
        query_context.business_knowledge,
        start=1,
    ):
        document = item.document

        print(
            f"{index}. "
            f"id={document.document_id}"
        )
        print(
            f"   score={item.score}"
        )
        print(
            f"   text={document.text}"
        )

    print(
        "\n[Verified SQL]"
    )

    if not query_context.verified_sql:
        print("None")

    for index, item in enumerate(
        query_context.verified_sql,
        start=1,
    ):
        document = item.document

        print(
            f"{index}. "
            f"id={document.document_id}"
        )
        print(
            f"   score={item.score}"
        )
        print(
            f"   text={document.text}"
        )


def print_case(
    *,
    case,
    state: dict,
    evaluation,
) -> None:

    print()
    print("=" * 88)
    print(
        f"CASE: {case.case_id}"
    )
    print("=" * 88)

    # ========================================================
    # Question / Behavior
    # ========================================================

    print(
        "\n[Question]"
    )
    print(case.question)

    print(
        "\n[Behavior]"
    )
    print(
        "Expected:",
        case.expected_behavior.value,
    )
    print(
        "Actual:",
        evaluation.actual_behavior.value,
    )
    print(
        "Correct:",
        evaluation.behavior_correct,
    )

    # ========================================================
    # Golden Plan
    # ========================================================

    print(
        "\n[Expected Plan]"
    )

    print(
        "Tables:",
        case.expected_tables,
    )

    print(
        "Dimensions:",
        case.expected_dimensions,
    )

    print(
        "Metrics:",
        case.expected_metrics,
    )

    print(
        "Filters:",
        case.expected_filters,
    )

    print(
        "GroupBy:",
        case.expected_group_by,
    )

    # ========================================================
    # Actual Plan
    # ========================================================

    print(
        "\n[Actual Plan]"
    )

    query_plan = state.get(
        "query_plan"
    )

    if query_plan is None:
        print("None")
    else:
        print(
            "Tables:",
            query_plan.tables,
        )

        print(
            "Dimensions:",
            query_plan.dimensions,
        )

        print(
            "Metrics:",
            query_plan.metrics,
        )

        print(
            "Filters:",
            query_plan.filters,
        )

        print(
            "GroupBy:",
            query_plan.group_by,
        )

        print(
            "Requirements:",
            query_plan.requirements,
        )

    # ========================================================
    # Evaluator Diagnosis
    # ========================================================

    print(
        "\n[Evaluator]"
    )

    print(
        "Table correct:",
        evaluation.table_selection_correct,
    )

    print(
        "Dimension correct:",
        evaluation.dimension_selection_correct,
    )

    print(
        "Metric correct:",
        evaluation.metric_selection_correct,
    )

    print(
        "Filter correct:",
        evaluation.filter_selection_correct,
    )

    print(
        "GroupBy correct:",
        evaluation.group_by_correct,
    )

    print(
        "Pipeline success:",
        evaluation.pipeline_success,
    )

    print(
        "Trusted SQL available:",
        evaluation.trusted_sql_available,
    )

    print(
        "Case PASSED:",
        evaluation.passed,
    )

    # ========================================================
    # Clarification
    # ========================================================

    print(
        "\n[Clarification]"
    )

    print(
        "Question:",
        evaluation.clarification_question,
    )

    print(
        "Missing context:",
        state.get(
            "missing_context"
        ),
    )

    print(
        "Reason:",
        state.get(
            "clarification_reason"
        ),
    )

    # ========================================================
    # SQL
    # ========================================================

    print(
        "\n[SQL]"
    )

    print(
        "Generated SQL:"
    )
    print(
        state.get(
            "generated_sql"
        )
    )

    print(
        "\nCandidate SQL:"
    )
    print(
        state.get(
            "candidate_sql"
        )
    )

    print(
        "\nTrusted SQL:"
    )
    print(
        state.get(
            "trusted_sql"
        )
    )

    # ========================================================
    # Validation
    # ========================================================

    print(
        "\n[Validation]"
    )

    print(
        "Deterministic status:",
        status_text(
            state.get(
                "validation_status"
            )
        ),
    )

    print(
        "Semantic status:",
        status_text(
            state.get(
                "semantic_validation_status"
            )
        ),
    )

    semantic_result = state.get(
        "semantic_result"
    )

    if semantic_result is None:
        print(
            "Semantic missing requirements:",
            None,
        )
        print(
            "Semantic issues:",
            None,
        )
    else:
        print(
            "Semantic missing requirements:",
            semantic_result.missing_requirements,
        )

        print(
            "Semantic issues:",
            semantic_result.issues,
        )

    # ========================================================
    # Retrieval
    # ========================================================

    print_retrieval(
        state
    )

def _accuracy(
    values,
) -> tuple[int, int, float]:

    valid = [
        value
        for value in values
        if value is not None
    ]

    if not valid:
        return 0, 0, 0.0

    correct = sum(
        value is True
        for value in valid
    )

    total = len(valid)

    return (
        correct,
        total,
        correct / total,
    )


def _print_metric(
    name: str,
    values,
) -> None:

    correct, total, rate = (
        _accuracy(values)
    )

    print(
        f"{name:<28}"
        f"{correct}/{total} "
        f"({rate:.1%})"
    )


def main() -> None:

    graph = build_graph()

    evaluator = (
        TextToSQLEvaluator()
    )

    # 不再筛选失败Case。
    # Text-to-SQL最终Gate必须跑全部Golden。
    cases = tuple(
        TEXT_TO_SQL_GOLDEN_V0_1
    )

    results = []

    print()
    print("=" * 88)
    print(
        "Agent3.0 "
        "Text-to-SQL V1 Final Evaluation"
    )
    print("=" * 88)

    for case in cases:

        state = graph.start(
            thread_id=(
                "final-eval-"
                f"{case.case_id}-"
                f"{uuid4().hex}"
            ),

            question=(
                case.question
            ),
        )

        response = (
            state_to_response(
                question=(
                    case.question
                ),
                state=state,
            )
        )

        evaluation = (
            evaluator.evaluate(
                case=case,
                actual=response,
            )
        )

        results.append(
            (
                case,
                state,
                evaluation,
            )
        )

        status = (
            "PASS"
            if evaluation.passed
            else "FAIL"
        )

        print(
            f"{case.case_id:<45}"
            f"{status}"
        )

    print()
    print("=" * 88)
    print("Summary")
    print("=" * 88)

    total_cases = len(results)

    passed_cases = sum(
        evaluation.passed
        for _, _, evaluation
        in results
    )

    print(
        f"Cases:                       "
        f"{passed_cases}/{total_cases} "
        f"({passed_cases / total_cases:.1%})"
    )

    print()

    _print_metric(
        "Behavior accuracy:",
        [
            evaluation.behavior_correct
            for _, _, evaluation
            in results
        ],
    )

    _print_metric(
        "Table accuracy:",
        [
            evaluation.table_selection_correct
            for _, _, evaluation
            in results
        ],
    )

    _print_metric(
        "Dimension diagnostic:",
        [
            evaluation.dimension_selection_correct
            for _, _, evaluation
            in results
        ],
    )

    _print_metric(
        "Metric accuracy:",
        [
            evaluation.metric_selection_correct
            for _, _, evaluation
            in results
        ],
    )

    _print_metric(
        "Filter accuracy:",
        [
            evaluation.filter_selection_correct
            for _, _, evaluation
            in results
        ],
    )

    _print_metric(
        "GroupBy diagnostic:",
        [
            evaluation.group_by_correct
            for _, _, evaluation
            in results
        ],
    )

    _print_metric(
        "Pipeline success:",
        [
            evaluation.pipeline_success
            for _, _, evaluation
            in results
        ],
    )

    _print_metric(
        "Trusted SQL expectation:",
        [
            evaluation
            .trusted_sql_expectation_met
            for _, _, evaluation
            in results
        ],
    )

    # ========================================================
    # Failure Analysis
    # ========================================================

    failures = [
        item
        for item in results
        if not item[2].passed
    ]

    print()
    print("=" * 88)
    print(
        f"Failures: {len(failures)}"
    )
    print("=" * 88)

    if not failures:
        print(
            "No failed Golden Cases."
        )

    for (
        case,
        state,
        evaluation,
    ) in failures:

        # 复用原来的详细诊断函数。
        print_case(
            case=case,
            state=state,
            evaluation=evaluation,
        )


if __name__ == "__main__":
    main()