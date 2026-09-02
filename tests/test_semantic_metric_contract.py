from __future__ import annotations

from pathlib import Path

from sql_pilot_engine.context.semantic.loader import (
    SemanticModelLoader,
)


def test_simple_metric_has_structured_contract(
) -> None:

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    model = (
        SemanticModelLoader()
        .load(
            project_root
            / "sql_pilot_engine"
            / "context"
            / "semantic"
            / "loan_model.json"
        )
    )

    metric = model.get_metric(
        "tech_loan_balance"
    )

    assert metric is not None

    assert (
        metric.table
        == "ods_hd_100_cldkxx"
    )

    assert (
        metric.aggregation
        == "sum"
    )

    assert (
        metric.source_column
        == "loan_bal_rmb"
    )

    assert (
        metric.fixed_filters
        == ()
    )


def test_complex_metric_can_remain_expression_only(
) -> None:

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    model = (
        SemanticModelLoader()
        .load(
            project_root
            / "sql_pilot_engine"
            / "context"
            / "semantic"
            / "loan_model.json"
        )
    )

    metric = model.get_metric(
        "tech_loan_weighted_rate"
    )

    assert metric is not None

    assert (
        metric.aggregation
        is None
    )

    assert (
        metric.source_column
        is None
    )

    assert (
        metric.expression
        == (
            "SUM(loan_bal_rmb * rate) "
            "/ SUM(loan_bal_rmb)"
        )
    )