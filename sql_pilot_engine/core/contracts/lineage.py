from __future__ import annotations

from typing import Protocol


class LineageStore(Protocol):
    """
    血缘存储接口。

    当前只留位。

    不实现:
    - 血缘解析
    - 图数据库
    - 影响分析
    """


    def get_downstream(
        self,
        object_id: str,
    ):
        ...


    def get_upstream(
        self,
        object_id: str,
    ):
        ...