
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from typing import Protocol, runtime_checkable


from sql_pilot_engine.metadata.models import TableLookupResult,TableMetadata,ColumnMetadata




@runtime_checkable
class MetadataProvider(Protocol):
    """元数据查询接口。

    Protocol采用结构化类型检查：
    一个类不必显式继承MetadataProvider，
    只要实现了相同的方法，就可以被视为Provider。

    这样可以避免业务层依赖某个具体数据库SDK。
    """
    
    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:
        """查询指定物理表的元数据"""
        ...
        

    
class BaseMetadataProvider(ABC):
    """元数据 Provider 抽象。"""

    @abstractmethod
    def get_table(self, table_name: str) -> TableMetadata | None:
        raise NotImplementedError

    def table_exists(self, table_name: str) -> bool:
        return self.get_table(table_name) is not None

    def column_exists(self, table_name: str, column_name: str) -> bool:
        table = self.get_table(table_name)
        if table is None:
            return False
        return column_name.lower() in table.column_names()


class MockMetadataProvider(BaseMetadataProvider):
    """基于 JSON 的 Mock 元数据 Provider。"""

    def __init__(self, metadata_file: str | Path | None = None) -> None:
        if metadata_file is None:
            metadata_file = Path(__file__).parent / "mock_metadata.json"

        self.metadata_file = Path(metadata_file)
        self.tables = self._load_tables()

    def _load_tables(self) -> dict[str, TableMetadata]:
        raw_data = json.loads(self.metadata_file.read_text(encoding="utf-8"))
        tables: dict[str, TableMetadata] = {}

        for item in raw_data.get("tables", []):
            table = TableMetadata(
                table_name=item["table_name"],
                layer=item.get("layer", "unknown"),
                is_partitioned=bool(item.get("is_partitioned", False)),
                partition_fields=list(item.get("partition_fields", [])),
                comment=item.get("comment", ""),
                columns=[
                    ColumnMetadata(
                        name=column["name"],
                        data_type=column.get("data_type", "string"),
                        comment=column.get("comment", ""),
                    )
                    for column in item.get("columns", [])
                ],
            )
            tables[table.table_name.lower()] = table

        return tables

    def get_table(self, table_name: str) -> TableMetadata | None:
        normalized = table_name.lower()
        table = self.tables.get(normalized)
        if table is not None:
            return table

        # 兼容 project.table / schema.table，只用最后一级表名兜底查询。
        simple_name = normalized.split(".")[-1]
        return self.tables.get(simple_name)
