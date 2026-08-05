

from __future__ import annotations
from sql_pilot_engine.metadata.models import TableLookupResult,TableMetadata,ColumnMetadata

from collections.abc import Iterable


class MockMetadataProvider():
    """用于本地开发和自动测试的虚拟元数据Provider。

    它遵守与未来生产Provider相同的get_table接口，
    因此ReviewService不需要区分当前使用的是
    Python字典还是企业元数据平台。
    """
    def __init__(
        self,
        tables: Iterable[TableMetadata] | None = None,
    ) -> None:
        """创建虚拟元数据目录。

        Iterable表示不仅可以传list，也可以传tuple、
        generator等任何可迭代对象。
        """
        
        source_tables = (
            list(tables)
            if tables is not None
            else self._build_default_tables()
        )   
        
        self._tables = {
            table.full_name.lower(): table
            for table in source_tables
        }
        
    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:
        """ 按完整表名查询元数据"""
        
        normalized_name = full_name.lower()
        
        table = self._tables.get(normalized_name)
        
        if table is None:
            return TableLookupResult.not_found()
        
        return TableLookupResult.found(table)
    
    
    @staticmethod
    def _build_default_tables() -> list[TableMetadata]:
        """构造本地开发所需的最小虚拟数据目录。

        这里的数据不是生产元数据，只用于验证：
        - 表名解析；
        - 表存在性判断；
        - 字段存在性判断；
        - Join别名解析。
        """

        return [
            TableMetadata(
                full_name="dwd_order_detail",
                description="订单明细事实表",
                columns={
                    "order_id": ColumnMetadata(
                        name="order_id",
                        data_type="string",
                        nullable=False,
                        description="订单编号",
                    ),
                    "user_id": ColumnMetadata(
                        name="user_id",
                        data_type="string",
                        nullable=False,
                        description="用户编号",
                    ),
                    "order_amount": ColumnMetadata(
                        name="order_amount",
                        data_type="decimal(18,2)",
                        nullable=False,
                        description="订单金额",
                    ),
                    "dt": ColumnMetadata(
                        name="dt",
                        data_type="string",
                        nullable=False,
                        description="业务日期分区",
                    ),
                },
            ),
            TableMetadata(
                full_name="dim_user",
                description="用户维度表",
                columns={
                    "user_id": ColumnMetadata(
                        name="user_id",
                        data_type="string",
                        nullable=False,
                    ),
                    "user_name": ColumnMetadata(
                        name="user_name",
                        data_type="string",
                    ),
                    "user_status": ColumnMetadata(
                        name="user_status",
                        data_type="string",
                    ),
                    "dt": ColumnMetadata(
                        name="dt",
                        data_type="string",
                    ),
                },
            ),
            TableMetadata(
                full_name="ads_order_summary",
                description="订单汇总结果表",
                partition_fields=("dt",),
                columns={
                    "user_id": ColumnMetadata(
                        name="user_id",
                        data_type="string",
                    ),
                    "order_count": ColumnMetadata(
                        name="order_count",
                        data_type="bigint",
                    ),
                    "order_amount": ColumnMetadata(
                        name="order_amount",
                        data_type="decimal(18,2)",
                    ),
                    "dt": ColumnMetadata(
                        name="dt",
                        data_type="string",
                    ),
                },
            ),
        ]