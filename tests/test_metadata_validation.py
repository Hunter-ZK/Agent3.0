from sql_pilot_engine.analysis import SQLParser
from sql_pilot_engine.analysis.facts import (
    SQLFactsExtractor,
)
from sql_pilot_engine.metadata import (
    MetadataValidator,
    MockMetadataProvider,
)


def build_facts(sql: str):
    parser = SQLParser()
    extractor = SQLFactsExtractor()

    parse_result = parser.parse(
        sql=sql,
        dialect="maxcompute",
    )

    assert parse_result.success is True

    return extractor.extract(parse_result)


def test_existing_tables_and_columns_should_pass():
    facts = build_facts(
        """
        SELECT
            o.order_id,
            o.order_amount,
            u.user_name
        FROM dwd_order_detail o
        JOIN dim_user u
          ON o.user_id = u.user_id
        """
    )

    validator = MetadataValidator()
    provider = MockMetadataProvider()

    issues = validator.validate(
        facts=facts,
        provider=provider,
    )

    assert issues == []


def test_missing_table_should_be_blocked():
    facts = build_facts(
        """
        SELECT user_id
        FROM dwd_missing_order
        """
    )

    issues = MetadataValidator().validate(
        facts=facts,
        provider=MockMetadataProvider(),
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "TABLE_NOT_FOUND"
    assert issues[0].blocking is True


def test_missing_qualified_column_should_be_blocked():
    facts = build_facts(
        """
        SELECT o.order_amout
        FROM dwd_order_detail o
        """
    )

    issues = MetadataValidator().validate(
        facts=facts,
        provider=MockMetadataProvider(),
    )

    issue_ids = {
        issue.rule_id
        for issue in issues
    }

    assert "COLUMN_NOT_FOUND" in issue_ids


def test_select_alias_should_not_be_validated_as_column():
    facts = build_facts(
        """
        SELECT
            user_id,
            SUM(order_amount) AS total_amount
        FROM dwd_order_detail
        GROUP BY user_id
        ORDER BY total_amount DESC
        """
    )

    issues = MetadataValidator().validate(
        facts=facts,
        provider=MockMetadataProvider(),
    )

    assert issues == []


def test_unqualified_multi_table_column_should_not_be_guessed():
    facts = build_facts(
        """
        SELECT user_id
        FROM dwd_order_detail o
        JOIN dim_user u
          ON o.user_id = u.user_id
        """
    )

    issues = MetadataValidator().validate(
        facts=facts,
        provider=MockMetadataProvider(),
    )

    assert issues == []