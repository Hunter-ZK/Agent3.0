import inspect

from sql_pilot_engine.analysis import SQLParser
from sql_pilot_engine.analysis.facts import (
    SQLFactsExtractor,
)
from sql_pilot_engine.app.factory import (
    build_sql_pilot_engine,
)
from sql_pilot_engine.engine import SQLPilotEngine
from sql_pilot_engine.metadata import (
    MetadataLookupStatus,
    MockMetadataProvider,
)
from sql_pilot_engine.schemas.requests import (
    SQLReviewRequest,
)


def test_metadata_provider_returns_structured_result():
    provider = MockMetadataProvider()

    lookup = provider.get_table(
        "dwd_order_detail"
    )

    assert (
        lookup.status
        == MetadataLookupStatus.FOUND
    )
    assert lookup.table is not None
    assert "user_id" in lookup.table.column_names()


def test_engine_factory_builds_complete_dependencies():
    engine = build_sql_pilot_engine()

    assert isinstance(engine, SQLPilotEngine)
    assert engine.review_service is not None
    assert engine.fix_service is not None
    assert engine.critic_service is not None


def test_engine_review_uses_new_metadata_contract():
    engine = build_sql_pilot_engine()

    response = engine.review(
        SQLReviewRequest(
            sql=(
                "SELECT "
                "o.user_id, "
                "o.order_amount "
                "FROM dwd_order_detail o"
            ),
            enable_metadata=True,
        )
    )

    assert response.success is True

    issue_ids = {
        issue["rule_id"]
        for issue in response.issues
    }

    assert "TABLE_NOT_FOUND" not in issue_ids
    assert "COLUMN_NOT_FOUND" not in issue_ids
    assert "METADATA_LOOKUP_FAILED" not in issue_ids


def test_previous_statement_target_can_be_later_source():
    parser = SQLParser()
    extractor = SQLFactsExtractor()

    parse_result = parser.parse(
        sql=(
            "INSERT INTO ads_order_summary "
            "SELECT "
            "user_id, "
            "COUNT(*) AS order_count, "
            "SUM(order_amount) AS order_amount, "
            "dt "
            "FROM dwd_order_detail "
            "GROUP BY user_id, dt; "
            ""
            "SELECT user_id "
            "FROM ads_order_summary;"
        ),
        dialect="maxcompute",
    )

    assert parse_result.success is True

    facts = extractor.extract(
        parse_result=parse_result,
    )

    assert "dwd_order_detail" in facts.source_tables
    assert "ads_order_summary" in facts.source_tables
    assert "ads_order_summary" in facts.target_tables


def test_critique_keyword_matches_workflow_contract():
    parameters = inspect.signature(
        SQLPilotEngine.critique
    ).parameters

    assert "fix_response" in parameters