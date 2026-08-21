from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(
    frozen=True,
    slots=True,
)
class TableSearchResult:
    full_name: str
    description: str
    layer: str


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnSearchResult:
    table_full_name: str
    table_description: str

    column_name: str
    column_description: str

    data_type: str


class MetadataCatalog(Protocol):
    """
    元数据资产发现接口。

    与MetadataProvider不同：
    Provider用于确定性表校验；
    Catalog用于搜索已有数据资产。
    """

    def find_tables(
        self,
        keyword: str,
        *,
        limit: int = 20,
    ) -> tuple[
        TableSearchResult,
        ...
    ]:
        ...

    def find_columns(
        self,
        keyword: str,
        *,
        limit: int = 50,
    ) -> tuple[
        ColumnSearchResult,
        ...
    ]:
        ...

    def find_column_usages(
        self,
        column_name: str,
    ) -> tuple[
        ColumnSearchResult,
        ...
    ]:
        """
        查询一个精确字段名在全部物理表中的使用情况。

        这是 Complete Fact Query，
        不允许使用隐式 Top-N limit。
        """
        ...