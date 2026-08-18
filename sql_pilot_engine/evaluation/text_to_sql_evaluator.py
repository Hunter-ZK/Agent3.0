from __future__ import annotations

from collections.abc import Iterable

from sql_pilot_engine.evaluation.models import (
    ActualAgentBehavior,
    ExpectedAgentBehavior,
    GoldenTextToSQLCase,
    TextToSQLEvaluation,
    TextToSQLEvaluationSummary,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLResponse,
    TextToSQLResult,
)


def _normalize_names(
    values: Iterable[str],
) -> frozenset[str]:
    """名称集合归一化。

    V0.1只处理：
    - 首尾空格
    - 大小写

    暂不处理：
    - 同义词
    - schema.table差异
    - metric alias
    """
    return frozenset(
        value.strip().lower()
        for value in values
        if value.strip()
    )


def _normalize_filters(
    values: Iterable[str],
) -> frozenset[str]:
    """Filter V0.1归一化。

    当前只消除：
    - 大小写差异
    - 空白字符差异

    暂时不尝试判断：
    a = 1
    与
    1 = a

    是否语义等价。
    """
    return frozenset(
        "".join(
            value.lower().split()
        )
        for value in values
        if value.strip()
    )


class TextToSQLEvaluator:
    """评价Agent行为及Text-to-SQL结果。"""

    def evaluate(
        self,
        *,
        case: GoldenTextToSQLCase,
        actual: TextToSQLResponse,
    ) -> TextToSQLEvaluation:

        self._validate_case_alignment(
            case=case,
            actual=actual,
        )

        if isinstance(
            actual,
            TextToSQLClarification,
        ):
            return (
                self._evaluate_clarification(
                    case=case,
                    actual=actual,
                )
            )

        return self._evaluate_answer(
            case=case,
            actual=actual,
        )

    def _evaluate_clarification(
        self,
        *,
        case: GoldenTextToSQLCase,
        actual: TextToSQLClarification,
    ) -> TextToSQLEvaluation:

        behavior_correct = (
            case.expected_behavior
            is ExpectedAgentBehavior.CLARIFY
        )

        return TextToSQLEvaluation(
            case_id=case.case_id,

            expected_behavior=(
                case.expected_behavior
            ),

            actual_behavior=(
                ActualAgentBehavior.CLARIFY
            ),

            behavior_correct=(
                behavior_correct
            ),

            table_selection_correct=None,
            dimension_selection_correct=None,
            metric_selection_correct=None,
            filter_selection_correct=None,
            group_by_correct=None,

            pipeline_success=None,
            trusted_sql_available=None,
            trusted_sql_expectation_met=None,

            validation_status=None,
            semantic_validation_status=None,

            passed=behavior_correct,

            clarification_question=(
                actual.clarification_question
            ),
        )

    def _evaluate_answer(
        self,
        *,
        case: GoldenTextToSQLCase,
        actual: TextToSQLResult,
    ) -> TextToSQLEvaluation:

        behavior_correct = (
            case.expected_behavior
            is ExpectedAgentBehavior.ANSWER
        )
        
        if not behavior_correct:
            return TextToSQLEvaluation(
                case_id=case.case_id,

                expected_behavior=(
                    case.expected_behavior
                ),

                actual_behavior=(
                    ActualAgentBehavior.ANSWER
                ),

                behavior_correct=False,

                table_selection_correct=None,
                dimension_selection_correct=None,
                metric_selection_correct=None,
                filter_selection_correct=None,
                group_by_correct=None,

                pipeline_success=actual.success,

                trusted_sql_available=bool(
                    actual.trusted_sql
                    and actual.trusted_sql.strip()
                ),

                trusted_sql_expectation_met=None,

                validation_status=(
                    actual.validation_status
                ),

                semantic_validation_status=(
                    actual.semantic_validation_status
                ),

                passed=False,
            )

        plan = actual.query_plan

        table_selection_correct = (
            _normalize_names(
                plan.tables
            )
            == _normalize_names(
                case.expected_tables
            )
        )

        dimension_selection_correct = (
            _normalize_names(
                plan.dimensions
            )
            == _normalize_names(
                case.expected_dimensions
            )
        )

        metric_selection_correct = (
            _normalize_names(
                plan.metrics
            )
            == _normalize_names(
                case.expected_metrics
            )
        )

        filter_selection_correct = (
            _normalize_filters(
                plan.filters
            )
            == _normalize_filters(
                case.expected_filters
            )
        )

        group_by_correct = (
            _normalize_names(
                plan.group_by
            )
            == _normalize_names(
                case.expected_group_by
            )
        )

        trusted_sql_available = bool(
            actual.trusted_sql
            and actual.trusted_sql.strip()
        )

        trusted_sql_expectation_met = (
            trusted_sql_available
            == case.expected_trusted_sql
        )

        passed = all(
            (
                behavior_correct,
                table_selection_correct,
                dimension_selection_correct,
                metric_selection_correct,
                filter_selection_correct,
                group_by_correct,
                actual.success,
                trusted_sql_expectation_met,
            )
        )

        return TextToSQLEvaluation(
            case_id=case.case_id,

            expected_behavior=(
                case.expected_behavior
            ),

            actual_behavior=(
                ActualAgentBehavior.ANSWER
            ),

            behavior_correct=(
                behavior_correct
            ),
            
            actual_tables=tuple(
                plan.tables
            ),

            actual_dimensions=tuple(
                plan.dimensions
            ),

            actual_metrics=tuple(
                plan.metrics
            ),

            actual_filters=tuple(
                plan.filters
            ),

            actual_group_by=tuple(
                plan.group_by
            ),

            table_selection_correct=(
                table_selection_correct
            ),

            dimension_selection_correct=(
                dimension_selection_correct
            ),

            metric_selection_correct=(
                metric_selection_correct
            ),

            filter_selection_correct=(
                filter_selection_correct
            ),

            group_by_correct=(
                group_by_correct
            ),

            pipeline_success=(
                actual.success
            ),

            trusted_sql_available=(
                trusted_sql_available
            ),

            trusted_sql_expectation_met=(
                trusted_sql_expectation_met
            ),

            validation_status=(
                actual.validation_status
            ),

            semantic_validation_status=(
                actual.semantic_validation_status
            ),

            passed=passed,
        )

    def summarize(
        self,
        results: Iterable[
            TextToSQLEvaluation
        ],
    ) -> TextToSQLEvaluationSummary:

        items = tuple(results)

        if not items:
            raise ValueError(
                "evaluation results "
                "must not be empty"
            )

        total = len(items)

        error_cases = sum(
            item.actual_behavior
            is ActualAgentBehavior.ERROR
            for item in items
        )

        answer_cases = sum(
            item.expected_behavior
            is ExpectedAgentBehavior.ANSWER
            for item in items
        )

        clarification_cases = sum(
            item.expected_behavior
            is ExpectedAgentBehavior.CLARIFY
            for item in items
        )

        return TextToSQLEvaluationSummary(
            total_cases=total,

            answer_cases=answer_cases,

            clarification_cases=(
                clarification_cases
            ),

            error_cases=error_cases,

            pass_rate=self._rate(
                item.passed
                for item in items
            ),

            error_rate=(
                error_cases / total
            ),

            behavior_accuracy=self._rate(
                item.behavior_correct
                for item in items
            ),

            table_selection_accuracy=(
                self._optional_rate(
                    item.table_selection_correct
                    for item in items
                )
            ),

            dimension_selection_accuracy=(
                self._optional_rate(
                    item.dimension_selection_correct
                    for item in items
                )
            ),

            metric_selection_accuracy=(
                self._optional_rate(
                    item.metric_selection_correct
                    for item in items
                )
            ),

            filter_selection_accuracy=(
                self._optional_rate(
                    item.filter_selection_correct
                    for item in items
                )
            ),

            group_by_accuracy=(
                self._optional_rate(
                    item.group_by_correct
                    for item in items
                )
            ),

            pipeline_success_rate=(
                self._optional_rate(
                    item.pipeline_success
                    for item in items
                )
            ),

            trusted_sql_rate=(
                self._optional_rate(
                    item.trusted_sql_available
                    for item in items
                )
            ),
        )

    @staticmethod
    def _rate(
        values: Iterable[bool],
    ) -> float:
        items = tuple(values)

        if not items:
            return 0.0

        return (
            sum(items)
            / len(items)
        )

    @staticmethod
    def _optional_rate(
        values: Iterable[
            bool | None
        ],
    ) -> float:
        """只统计适用的评分项。"""

        applicable = tuple(
            value
            for value in values
            if value is not None
        )

        if not applicable:
            return 0.0

        return (
            sum(applicable)
            / len(applicable)
        )

    @staticmethod
    def _validate_case_alignment(
        *,
        case: GoldenTextToSQLCase,
        actual: TextToSQLResponse,
    ) -> None:
        """防止拿错Result给Golden Case打分。"""

        if (
            case.question.strip()
            != actual.question.strip()
        ):
            raise ValueError(
                "Golden case question "
                "does not match actual result"
            )