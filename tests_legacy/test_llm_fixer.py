from sql_pilot_engine.llm.clients import MockLLMClient
from sql_pilot_engine.metadata import MockMetadataProvider
from sql_pilot_engine.services.review_service import ReviewService


def test_llm_fix_should_return_fixed_sql_result_with_mock_client():
    sql = """
    insert overwrite dws_user_trade_summary
    select user_id, sum(pay_amount) as total_pay_amount
    from dwd_user_order_detail
    where dt = '20260601'
    group by user_id
    """
    service = ReviewService(llm_client=MockLLMClient())
    result = service.review_sql(sql=sql, metadata_provider=MockMetadataProvider(), fix_sql=True, fix_provider="llm")
    assert result.fixed_sql_result is not None
    assert result.fixed_sql_result.source == "llm"
    assert "insert overwrite table" in result.fixed_sql_result.fixed_sql.lower()
    assert "dt = '${bizdate}'" in result.fixed_sql_result.fixed_sql


def test_llm_fix_should_fallback_to_auto_when_no_client():
    sql = "insert overwrite dws_user_trade_summary select user_id from dwd_user_order_detail where dt = '20260601'"
    result = ReviewService().review_sql(sql=sql, fix_sql=True, fix_provider="llm")
    assert result.fixed_sql_result is not None
    assert result.fixed_sql_result.source == "auto"
    assert "insert overwrite table" in result.fixed_sql_result.fixed_sql.lower()
