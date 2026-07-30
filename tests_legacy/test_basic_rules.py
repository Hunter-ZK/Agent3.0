from sql_pilot_engine.services.review_service import ReviewService


def ids(result):
    return [issue.rule_id for issue in result.issues]


def test_select_star_should_be_detected():
    result = ReviewService().review_sql("select * from dwd_user_order_detail")
    assert "SELECT_STAR" in ids(result)


def test_insert_overwrite_without_table_should_be_detected():
    sql = "insert overwrite dws_user_trade_summary select user_id from dwd_user_order_detail"
    result = ReviewService().review_sql(sql)
    assert "MAXCOMPUTE_INSERT_OVERWRITE_TABLE_REQUIRED" in ids(result)


def test_hardcoded_date_should_be_detected():
    sql = "select user_id from dwd_user_order_detail where dt = '20260601'"
    result = ReviewService().review_sql(sql)
    assert "DATAWORKS_HARDCODED_DATE" in ids(result)
