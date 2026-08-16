from sql_pilot_engine.observability.context import (
    bind_run_id,
    get_run_id,
)


def test_run_id_is_bound_inside_context() -> None:
    assert get_run_id() == "-"

    with bind_run_id("run-123"):
        assert get_run_id() == "run-123"

    assert get_run_id() == "-"


def test_nested_run_id_restores_previous_value() -> None:
    with bind_run_id("outer"):
        assert get_run_id() == "outer"

        with bind_run_id("inner"):
            assert get_run_id() == "inner"

        assert get_run_id() == "outer"