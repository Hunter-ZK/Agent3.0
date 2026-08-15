from __future__ import annotations

import logging
import os


DEFAULT_LOG_FORMAT = (
    "%(asctime)s "
    "%(levelname)s "
    "%(name)s "
    "%(message)s"
)


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

    logging.basicConfig(
        level=level,
        format=DEFAULT_LOG_FORMAT,
    )