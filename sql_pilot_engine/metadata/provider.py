
from __future__ import annotations


from typing import Protocol, runtime_checkable


from sql_pilot_engine.metadata.models import TableLookupResult




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
        
