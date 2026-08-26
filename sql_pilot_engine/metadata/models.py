from __future__ import annotations

from collections.abc import Mapping

from enum import Enum
from types import MappingProxyType

from dataclasses import dataclass



class MetadataLookupStatus(str, Enum):
    """元数据查询结果状态。

    FOUND：
        已找到目标表，并返回完整元数据。

    NOT_FOUND：
        元数据源正常工作，但确认目标表不存在。

    ERROR：
        元数据查询过程失败，例如网络异常、权限不足。
        ERROR不能等同于表不存在。
    """
    
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"



@dataclass(frozen=True)
class ColumnMetadata:
    """字段物理元数据。"""

    name: str
    data_type: str

    # None = Metadata Source 未提供该事实。
    nullable: bool | None = None

    description: str = ""

    # 后续由 DataWorks / Metadata API 提供。
    # 当前 Excel 没有该数据，因此保持 None。
    distinct_count: int | None = None



@dataclass(frozen=True)
class TableMetadata:
    """表物理元数据。"""

    full_name: str
    columns: Mapping[str, ColumnMetadata]

    partition_fields: tuple[str, ...] = ()

    description: str = ""

    layer: str = ""

    # Physical Stats。
    # 当前 Excel 不提供时统一保持 None。
    row_count: int | None = None

    size_bytes: int | None = None

    def __post_init__(self) -> None:
        normalized_columns = {
            name.lower(): column
            for name, column in self.columns.items()
        }

        normalized_partition_fields = tuple(
            field_name.lower()
            for field_name
            in self.partition_fields
        )

        object.__setattr__(
            self,
            "full_name",
            self.full_name.lower(),
        )

        object.__setattr__(
            self,
            "columns",
            normalized_columns,
        )

        object.__setattr__(
            self,
            "partition_fields",
            normalized_partition_fields,
        )

    def get_column(
        self,
        column_name: str,
    ) -> ColumnMetadata | None:
        return self.columns.get(
            column_name.lower()
        )

    def column_names(
        self,
    ) -> set[str]:
        return set(self.columns)

    @property
    def is_partitioned(
        self,
    ) -> bool:
        return bool(
            self.partition_fields
        )

    

@dataclass(frozen=True)
class TableLookupResult:
    '''MetadataProvider查询一张表后的统一响应'''
    
    status: MetadataLookupStatus
    
    table: TableMetadata | None = None
    error_message: str | None = None
    
    @classmethod
    def found(
        cls,
        table: TableMetadata,
    ) -> "TableLookupResult":
        
        return cls(
            status=MetadataLookupStatus.FOUND,
            table=table,
        )
    
    @classmethod
    def not_found(
        cls,
    ) -> "TableLookupResult":
        return cls(
            status=MetadataLookupStatus.NOT_FOUND,
        )
        
    @classmethod
    def failed(
        cls,
        error_message: str,
    ) -> "TableLookupResult":
        return cls(
            status=MetadataLookupStatus.ERROR,
            error_message=error_message,
        )
        
