from __future__ import annotations

from typing import Protocol, Sequence


class MetadataProvider(Protocol):
    """
    精确 Metadata 查询接口。

    服务:
    - SQL Validation
    - SQL Generation grounding

    特点:
    查询明确对象。

    例如:
    get_table("dwd_loan")
    """

    def get_table(
        self,
        table_name: str,
    ):
        ...


class MetadataCatalog(Protocol):
    """
    Metadata 探索接口。

    服务:
    - Context Intelligence
    - Asset QA
    - 模糊检索

    例如:
    用户问:
    "有哪些客户贷款相关表"
    """

    def find_tables(
        self,
        keyword: str,
    ) -> Sequence:
        ...


    def find_columns(
        self,
        keyword: str,
    ) -> Sequence:
        ...


class MetadataStatsProvider(Protocol):
    """
    元数据统计信息。

    F2 增加:
    - row_count
    - bytes
    - distinct_count
    """

    def get_stats(
        self,
        table_name: str,
    ):
        ...