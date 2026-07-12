from sql_review_agent.reporting.renderers import render_markdown
from sql_review_agent.services.review_service import ReviewService


def test_markdown_report_should_contain_summary():
    sql = "select * from dwd_user_order_detail where dt = '20260601'"
    result = ReviewService().review_sql(sql=sql)
    markdown = render_markdown(result)
    assert "# SQL Review Report" in markdown
    assert "## Review Summary" in markdown
    assert "SELECT_STAR" in markdown
    assert "DATAWORKS_HARDCODED_DATE" in markdown


def test_markdown_report_should_contain_fixed_sql_when_enabled():
    sql = """
    insert overwrite dws_user_trade_summary
    select user_id, sum(pay_amount) as total_pay_amount
    from dwd_user_order_detail
    where dt = '20260601'
    group by user_id
    """
    result = ReviewService().review_sql(sql=sql, fix_sql=True)
    markdown = render_markdown(result)
    assert "## Unified Fixed SQL" in markdown
    assert "insert overwrite table dws_user_trade_summary" in markdown.lower()
    assert "dt = '${bizdate}'" in markdown


def test_markdown_report_should_handle_no_issue_sql():
    sql = "select user_id, pay_amount from dwd_user_order_detail where dt = '${bizdate}'"
    result = ReviewService().review_sql(sql=sql)
    markdown = render_markdown(result)
    assert "# SQL Review Report" in markdown
    assert "## Issue Details" in markdown
