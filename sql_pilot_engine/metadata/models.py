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
    """字段元数据。"""

    name: str
    data_type: str
    
    nullable: bool = True
    description: str = ""
    # comment: str = ""


@dataclass(frozen=True)
class TableMetadata:
    """表元数据。"""

    full_name: str
    columns: Mapping[str, ColumnMetadata]
    
    # table_name: str
    # layer: str
    # is_partitioned: bool
    partition_fields: tuple[str, ...] = ()
    description: str = ""
    # comment: str = ""

    def __post_init__(self) -> None:
        """在dataclass完成初始化后执行标准化。

        为什么要转成小写：
        SQL中可能出现USER_ID、user_id、User_Id，
        但通常都应匹配同一个字段。

        为什么使用MappingProxyType：
        它把字典包装成只读映射，防止规则运行时
        意外修改共享元数据。

        为什么使用object.__setattr__：
        frozen=True禁止普通属性赋值，
        但__post_init__仍需完成标准化，因此通过
        object.__setattr__执行一次受控赋值。
        """
        
        normalized_columns = {
            name.lower(): column 
            for name, column in self.columns.items()
        }
        
        normalized_partition_fields = tuple(
            field_name.lower()
            for field_name in self.partition_fields
        )
        
        object.__setattr__(
            self,
            "full_name",
            self.full_name.lower()
        )
        
        object.__setattr__(
            self,
            "columns",
            MappingProxyType(normalized_columns),
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
        

    def column_names(self) -> set[str]:
        return {column.name.lower() for column in self.columns}
    
    
    @property
    def is_partitioned(self) -> bool:
        return bool(self.partition_fields)


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