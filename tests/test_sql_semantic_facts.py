from __future__ import annotations

from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
)


def test_extracts_simple_aggregate_facts(
) -> None:

    result = (
        SQLAnalysisAdapter()
        .analyze(
            sql="""
            SELECT
                SUM(loan_bal_rmb)
                    AS total_balance,
                COUNT(DISTINCT ent_code)
                    AS enterprise_count
            FROM ods_hd_100_cldkxx
            WHERE dt = '202607'
            """,

            dialect="maxcompute",
        )
    )

    assert result.facts is not None

    facts = result.facts

    by_function = {
        item.function: item
        for item
        in facts.aggregate_facts
    }

    assert (
        by_function[
            "sum"
        ]
        .column
        .name
        == "loan_bal_rmb"
    )

    assert (
        by_function[
            "count_distinct"
        ]
        .column
        .name
        == "ent_code"
    )


def test_complex_aggregate_is_not_claimed_as_simple_column(
) -> None:

    result = (
        SQLAnalysisAdapter()
        .analyze(
            sql="""
            SELECT
                SUM(
                    loan_bal_rmb * rate
                )
            FROM ods_hd_100_cldkxx
            """,

            dialect="maxcompute",
        )
    )

    assert result.facts is not None

    aggregate = (
        result
        .facts
        .aggregate_facts[0]
    )

    assert (
        aggregate.function
        == "sum"
    )

    assert (
        aggregate.column
        is None
    )


def test_extracts_where_predicate_facts(
) -> None:

    result = (
        SQLAnalysisAdapter()
        .analyze(
            sql="""
            SELECT
                SUM(loan_bal_rmb)
            FROM ods_hd_100_cldkxx
            WHERE
                dt = '202607'
                AND
                is_high_tech_mfg_loan_code
                    = '1'
            """,

            dialect="maxcompute",
        )
    )

    assert result.facts is not None

    predicates = {
        item.column.name: item
        for item
        in result
        .facts
        .predicate_facts
    }

    assert (
        predicates["dt"]
        .operator
        == "eq"
    )

    assert (
        predicates["dt"]
        .values
        == (
            "202607",
        )
    )

    assert (
        predicates[
            "is_high_tech_mfg_loan_code"
        ]
        .values
        == (
            "1",
        )
    )


def test_extracts_in_and_between_predicates(
) -> None:

    result = (
        SQLAnalysisAdapter()
        .analyze(
            sql="""
            SELECT *
            FROM ods_hd_100_cldkxx
            WHERE
                dt IN (
                    '202607',
                    '202608'
                )
                AND
                rate BETWEEN
                    1
                    AND 5
            """,

            dialect="maxcompute",
        )
    )

    assert result.facts is not None

    predicates = {
        (
            item.column.name,
            item.operator,
        ): item
        for item
        in result
        .facts
        .predicate_facts
    }

    assert (
        predicates[
            (
                "dt",
                "in",
            )
        ]
        .values
        == (
            "202607",
            "202608",
        )
    )

    assert (
        predicates[
            (
                "rate",
                "between",
            )
        ]
        .values
        == (
            1,
            5,
        )
    )