from sql_pilot_engine.app.factory import (
    build_workflow,
)


def test_clean_sql_completes():
    workflow = build_workflow(
        max_retries=0
    )

    result = workflow.run(
        """
        SELECT user_id
        FROM dwd_order_detail
        """,
        categories={"style"},
    )

    assert result.success is True
    assert result.final_status == "no_issue"

    assert result.review_response is not None
    assert result.review_response.issue_count == 0

    assert result.fix_response is None


def test_dangerous_sql_is_blocked():
    workflow = build_workflow(
        max_retries=0
    )

    result = workflow.run(
        "DROP TABLE important_table",
        categories={"safety"},
    )

    assert result.success is False
    assert result.final_status == "blocked"

    assert result.review_response is not None

    issue_ids = {
        issue["rule_id"]
        for issue
        in result.review_response.issues
    }

    assert "DROP_OR_TRUNCATE" in issue_ids


def test_auto_fix_re_review_and_critic():
    workflow = build_workflow(
        max_retries=0
    )

    result = workflow.run(
        """
        INSERT OVERWRITE ads_order_summary
        SELECT user_id
        FROM dwd_order_detail
        """,
        categories={"maxcompute"},
    )

    assert result.success is True
    assert result.final_status == "fix_verified"

    assert result.fix_response is not None
    assert result.fix_response.fixed_sql is not None

    assert (
        "INSERT OVERWRITE TABLE"
        in result.fix_response.fixed_sql.upper()
    )

    assert result.re_review_response is not None
    assert (
        result.re_review_response.issue_count
        == 0
    )

    assert result.critic_response is not None
    assert result.critic_response.passed is True