from __future__ import annotations

from collections.abc import Iterable

from sql_pilot_engine.evaluation.models import (
    GoldenTextToSQLCase,
    TextToSQLEvaluation,
    TextToSQLEvaluationSummary,
)

from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLResult,
)

def _normalize_names(
    values: Iterable[str],
) -> frozenset[str]:
    """将名称归一化后进行集合比较。

    V0.1只处理：
    - 大小写
    - 首尾空格

    暂时不处理：
    - 同义词
    - 表名前缀
    - schema.table
    - metric alias
    """

    return frozenset(
        value.strip().lower()
        for value in values 
        if value.strip()
    )
    


class TextToSQLEvaluator:

    def evaluate(
        self,
        *,
        case: GoldenTextToSQLCase,
        actual: TextToSQLResult,
    ) -> TextToSQLEvaluation:

        self._validate_case_alignment(
            case = case,
            actual = actual,
        )

        plan = actual.query_plan

        table_selection_correct = _normalize_names(plan.tables) == _normalize_names(case.expected_tables)
        dimension_selection_correct = _normalize_names(plan.dimensions) == _normalize_names(case.expected_dimensions)
        metric_selection_correct = _normalize_names(plan.metrics) == _normalize_names(case.expected_metrics)
        filter_selection_correct = _normalize_names(plan.filters) == _normalize_names(case.expected_filters)
        group_by_correct = _normalize_names(plan.group_by) == _normalize_names(case.expected_group_by)

        trusted_sql_available = bool(actual.trusted_sql and actual.trusted_sql.strip())

        trusted_sql_expectation_met = (trusted_sql_available == case.expected_trusted_sql)

        passed = all(
            (
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
            pipeline_success=actual.success,
            trusted_sql_available=(
                trusted_sql_available
            ),
            trusted_sql_expectation_met=(
                trusted_sql_expectation_met
            ),
            validation_status=(
                actual.validation_status
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
            item.error_message is not None
            for item in items
        )

        return TextToSQLEvaluationSummary(
            total_cases=total,

            error_cases=error_cases,

            pass_rate=self._rate(
                item.passed
                for item in items
            ),

            error_rate=(
                error_cases / total
            ),

            table_selection_accuracy=(
                self._rate(
                    item.table_selection_correct
                    for item in items
                )
            ),

            dimension_selection_accuracy=(
                self._rate(
                    item.dimension_selection_correct
                    for item in items
                )
            ),

            metric_selection_accuracy=(
                self._rate(
                    item.metric_selection_correct
                    for item in items
                )
            ),

            filter_accuracy=self._rate(
                item.filter_selection_correct
                for item in items
            ),

            group_by_accuracy=self._rate(
                item.group_by_correct
                for item in items
            ),

            pipeline_success_rate=self._rate(
                item.pipeline_success
                for item in items
            ),

            trusted_sql_rate=self._rate(
                item.trusted_sql_available
                for item in items
            ),
        )

    @staticmethod
    def _rate(
        values: Iterable[bool],
    ) -> float:
        items = tuple(values)

        return (
            sum(items)
            / len(items)
        )

    @staticmethod
    def _validate_case_alignment(
        *,
        case: GoldenTextToSQLCase,
        actual: TextToSQLResult,
    ) -> None:
        """防止拿错 Result 给 Golden Case 打分。"""

        if (
            case.question.strip()
            != actual.question.strip()
        ):
            raise ValueError(
                "Golden case question "
                "does not match actual result"
            )