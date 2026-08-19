from __future__ import annotations
from typing import Protocol, runtime_checkable

from sql_pilot_engine.metadata.models import (
    MetadataColumnMatch,
    MetadataSnapshot,
    MetadataTableMatch,
    TableLookupResult,
)

from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)


@runtime_checkable
class MetadataRepository(
    MetadataProvider,
    Protocol,
):
    """
    Shared Metadata持久化接口。

    与MetadataProvider的区别：

    MetadataProvider
        面向SQL Validation的窄查询接口。

    MetadataRepository
        面向整个DataAgent的元数据存储和发现接口。

    Repository继承Provider，
    因此任何Repository也可以直接供
    MetadataValidator使用。
    """
    
    def initialize(
        self,
    ) -> None:
        """
        初始化元数据存储结构
        """
        ...
        
    def import_snapshot(
        self,
        snapshot: MetadataSnapshot,
        *,
        activate: bool=True,
    ) -> int:
        """
        导入一份完整元数据快照。

        返回batch_id。
        """
        ...
        
    def find_tables(
        self,
        keyword: str,
        *,
        limit: int = 20,
    ) -> tuple[MetadataTableMatch, ...]:
        ...
        
    def find_columns(
        self,
        keyword: str,
        *,
        limit: int = 50,
    ) -> tuple[MetadataColumnMatch, ...]:
        ...
        
    def find_column_usages(
        self,
        column_name: str,
        *,
        limit: int = 100,
    ) -> tuple[
        MetadataColumnMatch,
        ...
    ]:
        ...