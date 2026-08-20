from __future__ import annotations

import sqlite3

from typing_extensions import (
    TypedDict,
)

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)
from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)
from sql_pilot_engine.runtime.checkpoint_sqlite import (
    SQLiteCheckpointStore,
)


class CounterState(
    TypedDict,
):
    value: int


def increment(
    state: CounterState,
) -> dict[str, int]:
    return {
        "value": (
            state["value"] + 1
        )
    }


def build_graph(
    checkpoint_store: CheckpointStore,
):
    builder = StateGraph(
        CounterState
    )

    builder.add_node(
        "increment",
        increment,
    )

    builder.add_edge(
        START,
        "increment",
    )

    builder.add_edge(
        "increment",
        END,
    )

    return builder.compile(
        checkpointer=(
            checkpoint_store
            .get_backend()
        )
    )


def test_memory_checkpoint_store_matches_contract():
    store = (
        MemoryCheckpointStore()
    )

    assert isinstance(
        store,
        CheckpointStore,
    )

    assert (
        store.get_backend()
        is not None
    )


def test_sqlite_checkpoint_store_matches_contract(
    tmp_path,
):
    store = SQLiteCheckpointStore(
        tmp_path
        / "checkpoints.db"
    )

    try:
        assert isinstance(
            store,
            CheckpointStore,
        )

        assert (
            store.get_backend()
            is not None
        )
    finally:
        store.close()


def test_sqlite_checkpoint_persists_across_reopen(
    tmp_path,
):
    database_path = (
        tmp_path
        / "checkpoints.db"
    )

    config = {
        "configurable": {
            "thread_id": (
                "persistent-thread"
            )
        }
    }

    first_store = (
        SQLiteCheckpointStore(
            database_path
        )
    )

    try:
        first_graph = build_graph(
            first_store
        )

        result = (
            first_graph.invoke(
                {
                    "value": 1
                },
                config=config,
            )
        )

        assert (
            result["value"]
            == 2
        )
    finally:
        first_store.close()

    assert database_path.exists()

    with sqlite3.connect(
        database_path
    ) as connection:
        journal_mode = (
            connection.execute(
                "PRAGMA journal_mode;"
            )
            .fetchone()[0]
        )

    assert (
        str(journal_mode).lower()
        == "wal"
    )

    second_store = (
        SQLiteCheckpointStore(
            database_path
        )
    )

    try:
        second_graph = build_graph(
            second_store
        )

        snapshot = (
            second_graph.get_state(
                config
            )
        )

        assert (
            snapshot.values[
                "value"
            ]
            == 2
        )
    finally:
        second_store.close()