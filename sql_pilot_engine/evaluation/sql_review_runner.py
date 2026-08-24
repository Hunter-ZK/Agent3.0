from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.evaluation.sql_review_cases import (
    SQLReviewGoldenCase,
)
from sql_pilot_engine.evaluation.sql_review_evaluator import (
    SQLReviewCaseEvaluation,
    SQLReviewEvaluator,
)
from sql_pilot_engine.schemas.sql_review import (
    SQLReviewInput,
)
from sql_pilot_engine.services.sql_review_service import (
    SQLReviewService,
)


@dataclass(
    frozen=True,
    slots=True,
)
class SQLReviewEvaluationSummary:
    total: int
    passed: int
    failed: int
    pass_rate: float

    cases: tuple[
        SQLReviewCaseEvaluation,
        ...,
    ]


class SQLReviewEvaluationRunner:

    def __init__(
        self,
        *,
        service: SQLReviewService,
        evaluator: (
            SQLReviewEvaluator | None
        ) = None,
    ) -> None:
        self._service = service

        self._evaluator = (
            evaluator
            or SQLReviewEvaluator()
        )

    def run(
        self,
        cases: tuple[
            SQLReviewGoldenCase,
            ...,
        ],
    ) -> SQLReviewEvaluationSummary:

        evaluations: list[
            SQLReviewCaseEvaluation
        ] = []

        for case in cases:

            result = (
                self._service.review(
                    SQLReviewInput(
                        sql=case.sql
                    )
                )
            )

            evaluation = (
                self._evaluator.evaluate(
                    case=case,
                    result=result,
                )
            )

            evaluations.append(
                evaluation
            )

        passed = sum(
            1
            for item in evaluations
            if item.passed
        )

        total = len(
            evaluations
        )

        failed = (
            total - passed
        )

        pass_rate = (
            passed / total
            if total
            else 0.0
        )

        return SQLReviewEvaluationSummary(
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            cases=tuple(
                evaluations
            ),
        )