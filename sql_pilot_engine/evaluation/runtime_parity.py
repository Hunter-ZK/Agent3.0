from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import uuid4

from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    GoldenTextToSQLCase,
    TextToSQLEvaluation,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
)
from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLRequest,
    TextToSQLResponse,
    TextToSQLResult,
)
from sql_pilot_engine.services.text_to_sql_service import (
    TextToSQLService,
)


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeParityCaseResult:
    """一条Golden Case的Runtime迁移对比结果。"""

    case_id: str

    python_evaluation: TextToSQLEvaluation
    langgraph_evaluation: TextToSQLEvaluation

    behavior_equal: bool

    tables_equal: bool | None
    dimensions_equal: bool | None
    metrics_equal: bool | None
    filters_equal: bool | None
    group_by_equal: bool | None

    pipeline_equal: bool | None
    trusted_sql_equal: bool | None

    parity_passed: bool


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeParityReport:
    """一次Python Runtime → LangGraph迁移验收结果。"""

    results: tuple[
        RuntimeParityCaseResult,
        ...
    ]

    total_cases: int
    passed_cases: int

    parity_rate: float

    python_pass_rate: float
    langgraph_pass_rate: float


class RuntimeParityRunner:
    """
    比较稳定Python Runtime和LangGraph Runtime。

    注意：
    Parity回答“迁移前后是否一致”。

    Golden Evaluation回答“结果本身是否正确”。

    两者不是同一个问题。
    """

    def __init__(
        self,
        *,
        python_service: TextToSQLService,
        langgraph: QueryAgentGraph,
        evaluator: TextToSQLEvaluator,
    ) -> None:
        self._python_service = (
            python_service
        )

        self._langgraph = langgraph

        self._evaluator = evaluator

    def run(
        self,
        cases: Iterable[
            GoldenTextToSQLCase
        ],
    ) -> RuntimeParityReport:

        items = tuple(cases)

        if not items:
            raise ValueError(
                "parity cases must not be empty"
            )

        results: list[
            RuntimeParityCaseResult
        ] = []

        for case in items:
            results.append(
                self._run_case(case)
            )

        passed_cases = sum(
            item.parity_passed
            for item in results
        )

        python_passed = sum(
            item.python_evaluation.passed
            for item in results
        )

        langgraph_passed = sum(
            item.langgraph_evaluation.passed
            for item in results
        )

        total = len(results)

        return RuntimeParityReport(
            results=tuple(results),

            total_cases=total,

            passed_cases=passed_cases,

            parity_rate=(
                passed_cases / total
            ),

            python_pass_rate=(
                python_passed / total
            ),

            langgraph_pass_rate=(
                langgraph_passed / total
            ),
        )

    def _run_case(
        self,
        case: GoldenTextToSQLCase,
    ) -> RuntimeParityCaseResult:

        request = TextToSQLRequest(
            question=case.question
        )

        python_evaluation = (
            self._evaluate_python(
                case=case,
                request=request,
            )
        )

        langgraph_evaluation = (
            self._evaluate_langgraph(
                case=case,
                request=request,
            )
        )

        return self._compare(
            case=case,

            python_evaluation=(
                python_evaluation
            ),

            langgraph_evaluation=(
                langgraph_evaluation
            ),
        )

    def _evaluate_python(
        self,
        *,
        case: GoldenTextToSQLCase,
        request: TextToSQLRequest,
    ) -> TextToSQLEvaluation:

        try:
            actual = (
                self._python_service
                .generate(request)
            )

            return self._evaluator.evaluate(
                case=case,
                actual=actual,
            )

        except Exception as exc:
            return self._error_result(
                case=case,
                error=exc,
            )

    def _evaluate_langgraph(
        self,
        *,
        case: GoldenTextToSQLCase,
        request: TextToSQLRequest,
    ) -> TextToSQLEvaluation:

        try:
            state = self._langgraph.start(
                thread_id=uuid4().hex,

                question=request.question,

                dialect=request.dialect,

                session_context=(
                    request.session_context
                ),
            )

            actual = (
                self._graph_state_to_response(
                    request=request,
                    state=state,
                )
            )

            return self._evaluator.evaluate(
                case=case,
                actual=actual,
            )

        except Exception as exc:
            return self._error_result(
                case=case,
                error=exc,
            )

    @staticmethod
    def _graph_state_to_response(
        *,
        request: TextToSQLRequest,
        state: dict,
    ) -> TextToSQLResponse:
        """
        QueryAgentGraph内部返回Graph State。

        Evaluation已经围绕统一的
        TextToSQLResponse工作。

        因此这里只做一次边界转换，
        不承担任何业务判断。
        """

        interrupts = state.get(
            "__interrupt__"
        )

        if interrupts:
            payload = getattr(
                interrupts[0],
                "value",
                None,
            )

            if not isinstance(
                payload,
                dict,
            ):
                raise RuntimeError(
                    "Invalid LangGraph "
                    "interrupt payload."
                )

            question = str(
                payload.get(
                    "question",
                    "",
                )
                or ""
            ).strip()

            if not question:
                raise RuntimeError(
                    "Clarification question "
                    "is missing."
                )

            return (
                TextToSQLClarification(
                    question=(
                        request.question
                    ),

                    clarification_question=(
                        question
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
            )

        query_plan = state.get(
            "query_plan"
        )

        if query_plan is None:
            raise RuntimeError(
                "LangGraph finished "
                "without QueryPlan "
                "or clarification."
            )

        semantic_result = state.get(
            "semantic_result"
        )

        return TextToSQLResult(
            question=request.question,

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

            validation_status=(
                RuntimeParityRunner
                ._status_text(
                    state.get(
                        "validation_status"
                    )
                )
            ),

            semantic_validation_status=(
                RuntimeParityRunner
                ._optional_status_text(
                    state.get(
                        "semantic_validation_status"
                    )
                )
            ),

            semantic_missing_requirements=(
                tuple(
                    getattr(
                        semantic_result,
                        "missing_requirements",
                        (),
                    )
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

    @staticmethod
    def _compare(
        *,
        case: GoldenTextToSQLCase,
        python_evaluation: TextToSQLEvaluation,
        langgraph_evaluation: TextToSQLEvaluation,
    ) -> RuntimeParityCaseResult:

        behavior_equal = (
            python_evaluation.actual_behavior
            is
            langgraph_evaluation.actual_behavior
        )

        # ERROR不能因为“两边都ERROR”
        # 就算迁移成功。
        if (
            python_evaluation.actual_behavior
            is ActualAgentBehavior.ERROR
            or
            langgraph_evaluation.actual_behavior
            is ActualAgentBehavior.ERROR
        ):
            return RuntimeParityCaseResult(
                case_id=case.case_id,

                python_evaluation=(
                    python_evaluation
                ),

                langgraph_evaluation=(
                    langgraph_evaluation
                ),

                behavior_equal=(
                    behavior_equal
                ),

                tables_equal=None,
                dimensions_equal=None,
                metrics_equal=None,
                filters_equal=None,
                group_by_equal=None,

                pipeline_equal=None,
                trusted_sql_equal=None,

                parity_passed=False,
            )

        if not behavior_equal:
            return RuntimeParityCaseResult(
                case_id=case.case_id,

                python_evaluation=(
                    python_evaluation
                ),

                langgraph_evaluation=(
                    langgraph_evaluation
                ),

                behavior_equal=False,

                tables_equal=None,
                dimensions_equal=None,
                metrics_equal=None,
                filters_equal=None,
                group_by_equal=None,

                pipeline_equal=None,
                trusted_sql_equal=None,

                parity_passed=False,
            )

        # 两边都选择CLARIFY。
        #
        # V0.1只判断行为一致，
        # 不要求LLM生成完全相同的追问文案。
        if (
            python_evaluation.actual_behavior
            is ActualAgentBehavior.CLARIFY
        ):
            return RuntimeParityCaseResult(
                case_id=case.case_id,

                python_evaluation=(
                    python_evaluation
                ),

                langgraph_evaluation=(
                    langgraph_evaluation
                ),

                behavior_equal=True,

                tables_equal=None,
                dimensions_equal=None,
                metrics_equal=None,
                filters_equal=None,
                group_by_equal=None,

                pipeline_equal=None,
                trusted_sql_equal=None,

                parity_passed=True,
            )

        tables_equal = (
            RuntimeParityRunner
            ._normalize_names(
                python_evaluation
                .actual_tables
            )
            ==
            RuntimeParityRunner
            ._normalize_names(
                langgraph_evaluation
                .actual_tables
            )
        )

        dimensions_equal = (
            RuntimeParityRunner
            ._normalize_names(
                python_evaluation
                .actual_dimensions
            )
            ==
            RuntimeParityRunner
            ._normalize_names(
                langgraph_evaluation
                .actual_dimensions
            )
        )

        metrics_equal = (
            RuntimeParityRunner
            ._normalize_names(
                python_evaluation
                .actual_metrics
            )
            ==
            RuntimeParityRunner
            ._normalize_names(
                langgraph_evaluation
                .actual_metrics
            )
        )

        filters_equal = (
            RuntimeParityRunner
            ._normalize_filters(
                python_evaluation
                .actual_filters
            )
            ==
            RuntimeParityRunner
            ._normalize_filters(
                langgraph_evaluation
                .actual_filters
            )
        )

        group_by_equal = (
            RuntimeParityRunner
            ._normalize_names(
                python_evaluation
                .actual_group_by
            )
            ==
            RuntimeParityRunner
            ._normalize_names(
                langgraph_evaluation
                .actual_group_by
            )
        )

        pipeline_equal = (
            python_evaluation
            .pipeline_success
            ==
            langgraph_evaluation
            .pipeline_success
        )

        trusted_sql_equal = (
            python_evaluation
            .trusted_sql_available
            ==
            langgraph_evaluation
            .trusted_sql_available
        )

        parity_passed = all(
            (
                behavior_equal,
                tables_equal,
                dimensions_equal,
                metrics_equal,
                filters_equal,
                group_by_equal,
                pipeline_equal,
                trusted_sql_equal,
            )
        )

        return RuntimeParityCaseResult(
            case_id=case.case_id,

            python_evaluation=(
                python_evaluation
            ),

            langgraph_evaluation=(
                langgraph_evaluation
            ),

            behavior_equal=(
                behavior_equal
            ),

            tables_equal=tables_equal,

            dimensions_equal=(
                dimensions_equal
            ),

            metrics_equal=metrics_equal,

            filters_equal=filters_equal,

            group_by_equal=(
                group_by_equal
            ),

            pipeline_equal=(
                pipeline_equal
            ),

            trusted_sql_equal=(
                trusted_sql_equal
            ),

            parity_passed=(
                parity_passed
            ),
        )

    @staticmethod
    def _normalize_names(
        values: Iterable[str],
    ) -> frozenset[str]:

        return frozenset(
            value.strip().lower()
            for value in values
            if value.strip()
        )

    @staticmethod
    def _normalize_filters(
        values: Iterable[str],
    ) -> frozenset[str]:

        return frozenset(
            "".join(
                value.lower().split()
            )
            for value in values
            if value.strip()
        )

    @staticmethod
    def _status_text(
        value,
    ) -> str:

        if value is None:
            return "not_run"

        enum_value = getattr(
            value,
            "value",
            None,
        )

        if enum_value is not None:
            return str(enum_value)

        return str(value)

    @staticmethod
    def _optional_status_text(
        value,
    ) -> str | None:

        if value is None:
            return None

        return (
            RuntimeParityRunner
            ._status_text(value)
        )

    @staticmethod
    def _error_result(
        *,
        case: GoldenTextToSQLCase,
        error: Exception,
    ) -> TextToSQLEvaluation:

        return TextToSQLEvaluation(
            case_id=case.case_id,

            expected_behavior=(
                case.expected_behavior
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
                "runtime_error"
            ),

            semantic_validation_status=None,

            passed=False,

            error_message=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )