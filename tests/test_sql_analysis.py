from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
)


def test_analysis_extracts_sql_facts():
    adapter = SQLAnalysisAdapter()

    result = adapter.analyze(
        """
        WITH order_summary AS (
            SELECT
                user_id,
                SUM(order_amount) AS total_amount
            FROM dwd_order_detail
            GROUP BY user_id
        )
        SELECT
            user_id,
            total_amount
        FROM order_summary
        """
    )

    assert result.success is True
    assert result.facts is not None

    assert (
        "dwd_order_detail"
        in result.facts.source_tables
    )

    assert (
        "order_summary"
        in result.facts.cte_names
    )


def test_analysis_failure_has_no_facts():
    adapter = SQLAnalysisAdapter()

    result = adapter.analyze(
        "SELECT FROM"
    )

    assert result.success is False
    assert result.facts is None


def test_analysis_detects_write_operation():
    adapter = SQLAnalysisAdapter()

    result = adapter.analyze(
        """
        INSERT INTO dws_user_day
        SELECT *
        FROM dwd_user_detail
        """
    )

    assert result.success is True
    assert result.facts is not None
    assert result.facts.has_write_operation is True