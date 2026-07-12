from sql_review_agent.llm.clients import MockLLMClient
from sql_review_agent.services.review_service import ReviewService


def ids(result):
    return [issue.rule_id for issue in result.issues]


def test_mock_llm_should_add_join_risk():
    sql = """
    select a.user_id, sum(a.pay_amount)
    from dwd_user_order_detail a
    join dim_city b on a.city_id = b.city_id
    group by a.user_id
    """
    service = ReviewService(llm_client=MockLLMClient())
    result = service.review_sql(sql, enable_llm=True)
    assert "LLM_JOIN_DUPLICATION_RISK" in ids(result)


def test_enable_llm_without_client_should_not_crash():
    result = ReviewService().review_sql("select 1", enable_llm=True)
    assert "LLM_REVIEW_FAILED" in ids(result)


def test_mock_llm_should_add_aggregation_null_suggestion():
    sql = "select user_id, sum(pay_amount) from dwd_user_order_detail group by user_id"
    service = ReviewService(llm_client=MockLLMClient())
    result = service.review_sql(sql, enable_llm=True)
    assert "LLM_AGGREGATION_NULL_HANDLING_SUGGESTION" in ids(result)
