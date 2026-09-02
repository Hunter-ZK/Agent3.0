from __future__ import annotations

import logging

from sql_pilot_engine.runtime.event import (
    RuntimeEvent,
    RuntimeEventType,
)

from sql_pilot_engine.runtime.event_bus import (
    DevEventSink,
)

from sql_pilot_engine.runtime.query_nodes import (
    QueryRuntimeNodes,
)


class RecordingEventBus:
    """
    测试用 EventBus。

    只记录收到的 RuntimeEvent。
    """

    def __init__(
        self,
    ) -> None:

        self.events: list[
            RuntimeEvent
        ] = []

    def publish(
        self,
        event: RuntimeEvent,
    ) -> None:

        self.events.append(
            event
        )


class FailingEventBus:
    """
    模拟 Observability
    基础设施故障。
    """

    def publish(
        self,
        event: RuntimeEvent,
    ) -> None:

        _ = event

        raise RuntimeError(
            "event sink unavailable"
        )


class UnusedStageService:
    """
    build_initial_state() 测试
    不会调用任何业务 Stage。
    """

    pass


def test_runtime_event_contract() -> None:

    event = RuntimeEvent(
        event_type=(
            RuntimeEventType.PLAN
        ),

        capability="text_to_sql",

        thread_id="thread-1",

        turn_id="turn-1",

        stage="planning",

        data={
            "status": "ready",
        },
    )

    assert (
        event.event_type
        is RuntimeEventType.PLAN
    )

    assert (
        event.capability
        == "text_to_sql"
    )

    assert (
        event.thread_id
        == "thread-1"
    )

    assert (
        event.turn_id
        == "turn-1"
    )

    assert (
        event.stage
        == "planning"
    )

    assert (
        event.data["status"]
        == "ready"
    )

    assert (
        event.occurred_at.tzinfo
        is not None
    )


def test_build_initial_state_emits_user_event(
) -> None:

    event_bus = (
        RecordingEventBus()
    )

    nodes = QueryRuntimeNodes(
        stage_service=(
            UnusedStageService()
        ),
        event_bus=event_bus,
    )

    state = (
        nodes.build_initial_state(
            thread_id="thread-1",

            question="test question",

            dialect="maxcompute",

            session_context=(),
        )
    )

    assert (
        "event_type"
        not in state
    )

    assert len(
        event_bus.events
    ) == 1

    event = (
        event_bus.events[0]
    )

    assert (
        event.event_type
        is RuntimeEventType
        .USER_MESSAGE
    )

    assert (
        event.thread_id
        == state["thread_id"]
    )

    assert (
        event.turn_id
        == state["turn_id"]
    )

    assert (
        event.stage
        == "input"
    )

    assert event.data == {
        "status": "received",
    }


def test_event_failure_does_not_break_runtime(
) -> None:

    nodes = QueryRuntimeNodes(
        stage_service=(
            UnusedStageService()
        ),

        event_bus=(
            FailingEventBus()
        ),
    )

    state = (
        nodes.build_initial_state(
            thread_id="thread-1",

            question="test question",

            dialect="maxcompute",

            session_context=(),
        )
    )

    assert (
        state["question"]
        == "test question"
    )

    assert (
        state["success"]
        is False
    )


def test_dev_event_sink_logs_event(
    caplog,
) -> None:

    logger = logging.getLogger(
        "tests.runtime.events"
    )

    sink = DevEventSink(
        logger=logger
    )

    event = RuntimeEvent(
        event_type=(
            RuntimeEventType
            .VALIDATION
        ),

        capability="text_to_sql",

        thread_id="thread-1",

        turn_id="turn-1",

        stage="trusted_sql",

        data={
            "status": "trusted",
        },
    )

    with caplog.at_level(
        logging.INFO,
        logger=logger.name,
    ):

        sink.publish(
            event
        )

    assert (
        "type=validation"
        in caplog.text
    )

    assert (
        "stage=trusted_sql"
        in caplog.text
    )

    assert (
        "thread_id=thread-1"
        in caplog.text
    )