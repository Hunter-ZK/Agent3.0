from __future__ import annotations

from sql_pilot_engine.app.sql_review_factory import build_sql_review_capability
from sql_pilot_engine.schemas.sql_review import SQLReviewInput


def test_trusted_sql_happy_path_returns_original_sql() -> None:
    capability = build_sql_review_capability()
    sql = "SELECT 1 AS ok"

    result = capability.review(SQLReviewInput(sql=sql))

    assert result.success is True
    assert result.trusted_sql == sql
    assert result.review_status in {"no_issue", "trusted_with_advisories"}
    assert result.fix_applied is False
    assert "review" in result.route_history


def test_trusted_sql_blocks_destructive_statement() -> None:
    capability = build_sql_review_capability()

    result = capability.review(
        SQLReviewInput(sql="DROP TABLE dangerous_table")
    )

    assert result.success is False
    assert result.trusted_sql is None
    assert result.review_status == "blocked"
    assert any(
        issue.rule_id == "DROP_OR_TRUNCATE"
        and issue.action == "block"
        for issue in result.issues
    )


def test_trusted_sql_auto_fixes_missing_maxcompute_table_keyword() -> None:
    capability = build_sql_review_capability()
    sql = "INSERT OVERWRITE target_table SELECT 1 AS id"

    result = capability.review(SQLReviewInput(sql=sql))

    assert result.success is True
    assert result.fix_applied is True
    assert result.review_status == "fixed"
    assert result.trusted_sql is not None
    assert "insert overwrite table target_table" in result.trusted_sql.lower()
    assert "fix" in result.route_history
    assert "re_review" in result.route_history
    assert "critic" in result.route_history
