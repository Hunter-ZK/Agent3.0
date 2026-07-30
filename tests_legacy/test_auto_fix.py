from sql_pilot_engine.metadata.provider import MockMetadataProvider
from sql_pilot_engine.services.review_service import ReviewService
from sql_pilot_engine.services.fix_service import FixService
from sql_pilot_engine.engine.sql_review_engine import SQLPilotEngine
from sql_pilot_engine.schemas.requests import SQLFixRequest



def build_engine():
    review_service = ReviewService()
    return SQLPilotEngine(review_service=review_service, fix_service=FixService(review_service))

def test_auto_fix_should_replace_hardcoded_date():
    sql = "select user_id from dwd_user_order_detail where dt = '20260601'"
    response = build_engine().fix(SQLFixRequest(sql=sql, fix_sql=True))

    assert response.success is True
    assert response.fixed_sql is not None
    assert response.fixed_sql_result is not None
    assert "dt = '${bizdate}'" in response.fixed_sql_result.fixed_sql


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

