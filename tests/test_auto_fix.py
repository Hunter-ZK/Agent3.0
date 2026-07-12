from sql_review_agent.metadata.provider import MockMetadataProvider
from sql_review_agent.services.review_service import ReviewService


def test_auto_fix_should_replace_hardcoded_date():
    sql = "select user_id from dwd_user_order_detail where dt = '20260601'"
    result = ReviewService().review_sql(sql=sql, fix_sql=True)
    assert result.fixed_sql_result is not None
    assert "dt = '${bizdate}'" in result.fixed_sql_result.fixed_sql


def test_auto_fix_should_add_insert_overwrite_table():
    sql = """
    insert overwrite dws_user_trade_summary
    select user_id, sum(pay_amount) as total_pay_amount
    from dwd_user_order_detail
    where dt = '${bizdate}'
    group by user_id
    """
    result = ReviewService().review_sql(sql=sql, fix_sql=True)
    assert result.fixed_sql_result is not None
    assert "insert overwrite table dws_user_trade_summary" in result.fixed_sql_result.fixed_sql.lower()


def test_auto_fix_should_add_partition_with_metadata():
    sql = """
    insert overwrite table dws_user_trade_summary
    select user_id, sum(pay_amount) as total_pay_amount
    from dwd_user_order_detail
    where dt = '${bizdate}'
    group by user_id
    """
    result = ReviewService().review_sql(sql=sql, metadata_provider=MockMetadataProvider(), fix_sql=True)
    assert result.fixed_sql_result is not None
    assert "partition(dt='${bizdate}')" in result.fixed_sql_result.fixed_sql.lower()


def test_auto_fix_should_add_todo_for_unknown_column():
    sql = "select user_id, pay_amt from dwd_user_order_detail where dt = '${bizdate}'"
    result = ReviewService().review_sql(sql=sql, metadata_provider=MockMetadataProvider(), fix_sql=True)
    assert result.fixed_sql_result is not None
    assert "AI_REVIEW_TODO" in result.fixed_sql_result.fixed_sql

