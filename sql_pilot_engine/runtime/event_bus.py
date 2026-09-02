from __future__ import annotations

import logging

from typing import Protocol

from sql_pilot_engine.runtime.event import (
    RuntimeEvent,
)

class EventBus(
    Protocol
):
    """
    Runtime 对事件输出能力
    所依赖的最小 Contract。

    Runtime 不知道：
    - Event 最终写日志；
    - 发网络；
    - 做 Evaluation；
    - 进入生产遥测系统。
    """

    def publish(
        self,
        event: RuntimeEvent,
    ) -> None:
        ...

class DevEventSink:
    """
    Runtime 对事件输出能力
    所依赖的最小 Contract。

    Runtime 不知道：
    - Event 最终写日志；
    - 发网络；
    - 做 Evaluation；
    - 进入生产遥测系统。
    """

    def __init__(
        self,
        *,
        logger: logging.Logge | None = None,
    ) -> None:

        self._logger = (
            logger
            if logger is not None
            else logging.getLogger(
                "sql_pilot_engine. runtime.events"
            )
        )

    def publish(
        self,
        event: RuntimeEvent,
    ) -> None:
        

        self._logger.info(
            (
                "agent_event "
                "type=%s "
                "capability=%s "
                "stage=%s "
                "thread_id=%s "
                "turn_id=%s "
                "occurred_at=%s "
                "data=%s"
            ),
            event.event_type.value,
            event.capability,
            event.stage,
            event.thread_id,
            event.turn_id,
            event.occurred_at.isoformat(),
            dict(event.data),
        )