from sqlglot import exp

from sql_pilot_engine.analysis import SQLParser


def test_parser_should_parse_select_sql():
    parser = SQLParser()

    result = parser.parse(
        sql=(
            "select user_id "
            "from dwd_user "
            "where dt = '${bizdate}'"
        ),
        dialect="maxcompute",
    )

    assert result.success is True
    assert result.statement_count == 1
    assert isinstance(
        result.first_statement,
        exp.Select,
    )


def test_parser_should_parse_multiple_statements():
    parser = SQLParser()

    result = parser.parse(
        sql="select 1; select 2;",
        dialect="maxcompute",
    )

    assert result.success is True
    assert result.statement_count == 2


def test_parser_should_reject_empty_sql():
    parser = SQLParser()

    result = parser.parse(
        sql="   ",
        dialect="maxcompute",
    )

    assert result.success is False
    assert result.error_message == (
        "SQL cannot be empty"
    )


def test_parser_should_return_parse_error():
    parser = SQLParser()

    result = parser.parse(
        sql="select from where",
        dialect="maxcompute",
    )

    assert result.success is False
    assert result.error_message