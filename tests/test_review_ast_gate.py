from sql_pilot_engine.services.review_service import (
    ReviewService,
)


def test_invalid_sql_should_return_blocking_issue():
    service = ReviewService()

    result = service.review_sql(
        sql="SELECT * FROM (",
        dialect="maxcompute",
    )

    assert result.issue_count == 1

    issue = result.issues[0]

    assert issue.rule_id == "SQL_PARSE_ERROR"
    assert issue.blocking is True
    assert issue.action.value == "block"


def test_select_star_should_be_detected_by_ast():
    service = ReviewService()

    result = service.review_sql(
        sql="SELECT * FROM dwd_order_detail",
        dialect="maxcompute",
    )

    issue_ids = {
        issue.rule_id
        for issue in result.issues
    }

    assert "SELECT_STAR" in issue_ids