from sql_pilot_engine.analysis import SQLParser
from sql_pilot_engine.analysis.facts import (
    SQLFactsExtractor,
)


def build_facts(sql: str):
    parser = SQLParser()
    extractor = SQLFactsExtractor()

    parse_result = parser.parse(
        sql=sql,
        dialect="maxcompute",
    )

    assert parse_result.success is True

    return extractor.extract(parse_result)


def test_should_extract_physical_tables_and_ctes():
    facts = build_facts(
        """
        WITH recent_order AS (
            SELECT order_id, user_id
            FROM dwd_order_detail
        )
        SELECT r.order_id, u.user_name
        FROM recent_order r
        JOIN dim_user u
          ON r.user_id = u.user_id
        """
    )

    assert facts.cte_names == ("recent_order",)
    assert facts.source_tables == (
        "dim_user",
        "dwd_order_detail",
    )


def test_should_detect_select_star_but_not_count_star():
    select_star = build_facts(
        "SELECT * FROM dwd_order_detail"
    )

    count_star = build_facts(
        "SELECT COUNT(*) FROM dwd_order_detail"
    )

    assert select_star.has_select_star is True
    assert count_star.has_select_star is False


def test_should_extract_insert_target_table():
    facts = build_facts(
        """
        INSERT OVERWRITE TABLE ads_order_summary
        SELECT user_id, COUNT(*) AS order_count
        FROM dwd_order_detail
        GROUP BY user_id
        """
    )

    assert facts.target_tables == (
        "ads_order_summary",
    )
    assert facts.source_tables == (
        "dwd_order_detail",
    )
    assert facts.has_write_operation is True


def test_should_detect_dangerous_statements():
    facts = build_facts(
        """
        DROP TABLE old_order;
        TRUNCATE TABLE temp_order;
        """
    )

    assert facts.has_drop is True
    assert facts.has_truncate is True
    assert facts.has_write_operation is True