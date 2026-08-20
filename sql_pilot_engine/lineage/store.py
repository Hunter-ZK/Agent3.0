from __future__ import annotations

from typing import Protocol


class LineageStore(Protocol):
    """
    血缘与影响分析的数据面接口占位。

    Ownership:
        Shared Data & Knowledge Plane

    当前阶段：
        仅预留接口所有权，不实现。

    明确禁止：
        - 挂到 MetadataRepository
        - 使用 metadata.db 存储血缘
        - 现在选择图数据库
        - 现在设计字段级血缘 DTO
        - 现在实现 SQL 全量血缘解析

    未来需求 3 启动后，
    再根据真实调度数据、SQL 脚本和影响分析需求
    设计具体 Contract 与 Storage。
    """

    pass