from __future__ import annotations

import logging
import os

from sql_pilot_engine.observability.context import (
    get_run_id,
)

class RunIdFilter(logging.Filter):

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:
        record.run_id = get_run_id()
        return True



def configure_logging() -> None:
    """配置 Agent3.0 的基础日志。

    默认 INFO。
    可以通过环境变量 AGENT3_LOG_LEVEL 修改：
    DEBUG / INFO / WARNING / ERROR
    """

    level_name = os.getenv(
        "AGENT3_LOG_LEVEL",
        "INFO",
    ).upper()

    level = getattr(
        logging,
        level_name,
        logging.INFO,
    )

    handler = logging.StreamHandler()

    handler.addFilter(RunIdFilter(),)

    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "run=%(run_id)s "
            "%(message)s"
        )
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

