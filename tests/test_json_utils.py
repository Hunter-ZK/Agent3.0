import pytest

from sql_review_agent.llm.json_utils import parse_json_object


def test_parse_json_object_should_parse_plain_json():
    payload = parse_json_object('{"sql_summary": "ok"}')

    assert payload["sql_summary"] == "ok"


def test_parse_json_object_should_parse_json_code_block():
    payload = parse_json_object(
        """
        ```json
        {"sql_summary": "ok"}
        ```
        """
    )

    assert payload["sql_summary"] == "ok"


def test_parse_json_object_should_reject_non_object_json():
    with pytest.raises(ValueError):
        parse_json_object('["not", "object"]')


def test_parse_json_object_should_raise_value_error_when_invalid():
    with pytest.raises(ValueError):
        parse_json_object("not json")
