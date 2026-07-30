from sql_pilot_engine.metadata.provider import MockMetadataProvider
from sql_pilot_engine.services.review_service import ReviewService


def ids(result):
    return [issue.rule_id for issue in result.issues]


def test_partitioned_insert_without_partition_should_be_detected():
    sql = """
    insert overwrite table dws_user_trade_summary
    select user_id, sum(pay_amount) as total_pay_amount
    from dwd_user_order_detail
    where dt = '${bizdate}'
    group by user_id
    """
    result = ReviewService().review_sql(sql, metadata_provider=MockMetadataProvider())
    assert "INSERT_WITHOUT_PARTITION" in ids(result)


def test_unknown_source_table_should_be_detected():
    sql = "select user_id from not_exists_table"
    result = ReviewService().review_sql(sql, metadata_provider=MockMetadataProvider())
    assert "UNKNOWN_SOURCE_TABLE" in ids(result)


def test_unknown_select_column_should_be_detected():
    sql = "select user_id, pay_amt from dwd_user_order_detail"
    result = ReviewService().review_sql(sql, metadata_provider=MockMetadataProvider())
    assert "UNKNOWN_COLUMN" in ids(result)
