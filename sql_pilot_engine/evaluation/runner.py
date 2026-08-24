from __future__ import annotations

import logging
import time

from collections.abc import Iterable
from dataclasses import dataclass

from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    GoldenTextToSQLCase,
    TextToSQLEvaluation,
    TextToSQLEvaluationSummary,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLRequest,
)
from sql_pilot_engine.capabilities.text_to_sql import (
    TextToSQLService,
)


logger = logging.getLogger(__name__)


@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLEvaluationReport:
    """一次完整批量评测的结果。"""

    results: tuple[
        TextToSQLEvaluation,
        ...
    ]

    summary: TextToSQLEvaluationSummary


class TextToSQLEvaluationRunner:
    """批量运行Agent / Text-to-SQL Golden Dataset。"""

    def __init__(
        self,
        *,
        service: TextToSQLService,
        evaluator: TextToSQLEvaluator,
    ) -> None:
        self._service = service
        self._evaluator = evaluator

    def run(
        self,
        cases: Iterable[
            GoldenTextToSQLCase
        ],
    ) -> TextToSQLEvaluationReport:

        items = tuple(cases)

        if not items:
            raise ValueError(
                "golden cases must not be empty"
            )

        logger.info(
            "evaluation.start cases=%d",
            len(items),
        )

        total_start = time.perf_counter()

        results: list[
            TextToSQLEvaluation
        ] = []

        for index, case in enumerate(
            items,
            start=1,
        ):
            result = self._run_case(
                case=case,
                index=index,
                total=len(items),
            )

            results.append(result)

        summary = (
            self._evaluator.summarize(
                results=results
            )
        )

        elapsed_ms = int(
            (
                time.perf_counter()
                - total_start
            )
            * 1000
        )

        logger.info(
            "evaluation.end "
            "cases=%d "
            "passed=%d "
            "errors=%d "
            "behavior_accuracy=%.3f "
            "elapsed_ms=%d",
            summary.total_cases,
            sum(
                result.passed
                for result in results
            ),
            summary.error_cases,
            summary.behavior_accuracy,
            elapsed_ms,
        )

        return TextToSQLEvaluationReport(
            results=tuple(results),
            summary=summary,
        )

    def _run_case(
        self,
        *,
        case: GoldenTextToSQLCase,
        index: int,
        total: int,
    ) -> TextToSQLEvaluation:

        logger.info(
            "evaluation.case.start "
            "case_id=%s "
            "expected_behavior=%s "
            "index=%d/%d",
            case.case_id,
            case.expected_behavior.value,
            index,
            total,
        )

        start = time.perf_counter()

        try:
            actual = self._service.generate(
                TextToSQLRequest(
                    question=case.question,
                )
            )

            evaluation = (
                self._evaluator.evaluate(
                    case=case,
                    actual=actual,
                )
            )

        except Exception as exc:
            logger.exception(
                "evaluation.case.error "
                "case_id=%s",
                case.case_id,
            )

            evaluation = (
                self._build_error_result(
                    case=case,
                    error=exc,
                )
            )

        elapsed_ms = int(
            (
                time.perf_counter()
                - start
            )
            * 1000
        )

        logger.info(
            "evaluation.case.end "
            "case_id=%s "
            "actual_behavior=%s "
            "passed=%s "
            "elapsed_ms=%d",
            case.case_id,
            evaluation.actual_behavior.value,
            evaluation.passed,
            elapsed_ms,
        )

        return evaluation

    @staticmethod
    def _build_error_result(
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
                "evaluation_error"
            ),

            semantic_validation_status=None,

            passed=False,

            error_message=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )