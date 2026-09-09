from __future__ import annotations

from collections.abc import (
    Iterable,
)

from sql_pilot_engine.metadata.models import (
    ColumnBusinessMetadata,
    ColumnManagementMetadata,
    ColumnMetadata,
    ColumnSemanticMetadata,
    ColumnTechnicalMetadata,
    TableBusinessMetadata,
    TableLookupResult,
    TableManagementMetadata,
    TableMetadata,
    TableOperationalMetadata,
    TableTechnicalMetadata,
)


class MockMetadataProvider:
    """
    用于本地开发和自动测试的虚拟 MetadataProvider。

    它遵守与正式 MetadataProvider 相同的：

        get_table(full_name)

    Contract。

    这里的数据属于 synthetic metadata，
    不代表正式生产 Metadata。
    """

    def __init__(
        self,
        tables: (
            Iterable[TableMetadata]
            | None
        ) = None,
    ) -> None:

        source_tables = (
            list(tables)
            if tables is not None
            else self._build_default_tables()
        )

        self._tables = {
            table.full_name: table
            for table
            in source_tables
        }

    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:
        """
        按传入表标识符执行精确查询。

        Mock Provider 不负责模糊搜索，
        也不负责 identifier disambiguation。
        """

        normalized_name = (
            full_name
            .strip()
            .lower()
        )

        table = self._tables.get(
            normalized_name
        )

        if table is None:
            return (
                TableLookupResult
                .not_found()
            )

        return (
            TableLookupResult
            .found(
                table
            )
        )

    @staticmethod
    def _build_default_tables(
    ) -> list[TableMetadata]:
        """
        构造本地开发所需的最小 synthetic Metadata。

        当前覆盖：

        dwd_order_detail
            订单明细事实表

        dim_user
            用户维度表

        ads_order_summary
            订单汇总结果表

        这些数据只用于验证：

        - 表存在性；
        - 字段存在性；
        - 字段类型；
        - Schema Linking；
        - SQL Generation；
        - Metadata Validation；
        - Partition Rule。
        """

        order_detail_columns = {
            "order_id": _column(
                name="order_id",
                ordinal_position=1,
                data_type="string",
                nullable=False,
                description="订单编号",
            ),
            "user_id": _column(
                name="user_id",
                ordinal_position=2,
                data_type="string",
                nullable=False,
                description="用户编号",
            ),
            "order_amount": _column(
                name="order_amount",
                ordinal_position=3,
                data_type="decimal(18,2)",
                nullable=False,
                description="订单金额",
            ),
            "dt": _column(
                name="dt",
                ordinal_position=4,
                data_type="string",
                nullable=False,
                description="业务日期",
            ),
        }

        user_columns = {
            "user_id": _column(
                name="user_id",
                ordinal_position=1,
                data_type="string",
                nullable=False,
                description="用户编号",
            ),
            "user_name": _column(
                name="user_name",
                ordinal_position=2,
                data_type="string",
                description="用户名称",
            ),
            "user_status": _column(
                name="user_status",
                ordinal_position=3,
                data_type="string",
                description="用户状态",
            ),
            "dt": _column(
                name="dt",
                ordinal_position=4,
                data_type="string",
                description="数据日期",
            ),
        }

        summary_columns = {
            "user_id": _column(
                name="user_id",
                ordinal_position=1,
                data_type="string",
                description="用户编号",
            ),
            "order_count": _column(
                name="order_count",
                ordinal_position=2,
                data_type="bigint",
                description="订单数量",
            ),
            "order_amount": _column(
                name="order_amount",
                ordinal_position=3,
                data_type="decimal(18,2)",
                description="订单金额",
            ),
            "dt": _column(
                name="dt",
                ordinal_position=4,
                data_type="string",
                description="数据日期分区",
                is_partition=True,
            ),
        }

        return [
            _table(
                full_name=(
                    "dwd_order_detail"
                ),
                description=(
                    "订单明细事实表"
                ),
                columns=(
                    order_detail_columns
                ),
            ),
            _table(
                full_name="dim_user",
                description="用户维度表",
                columns=user_columns,
            ),
            _table(
                full_name=(
                    "ads_order_summary"
                ),
                description=(
                    "订单汇总结果表"
                ),
                columns=(
                    summary_columns
                ),
                partition_fields=(
                    "dt",
                ),
            ),
        ]


def _column(
    *,
    name: str,
    ordinal_position: int,
    data_type: str,
    nullable: bool | None = None,
    description: str = "",
    is_partition: bool = False,
) -> ColumnMetadata:
    """
    MockMetadataProvider 内部专用字段构造函数。

    它不是正式 Metadata Factory，
    只负责减少 synthetic Metadata 的样板代码。
    """

    return ColumnMetadata(
        name=name,
        technical=(
            ColumnTechnicalMetadata(
                ordinal_position=(
                    ordinal_position
                ),
                data_type=data_type,
                nullable=nullable,
                is_partition=(
                    is_partition
                ),
            )
        ),
        business=(
            ColumnBusinessMetadata(
                description=(
                    description
                ),
            )
        ),
        semantic=(
            ColumnSemanticMetadata()
        ),
        management=(
            ColumnManagementMetadata()
        ),
    )


def _table(
    *,
    full_name: str,
    description: str,
    columns: dict[
        str,
        ColumnMetadata,
    ],
    partition_fields: tuple[
        str,
        ...,
    ] = (),
) -> TableMetadata:
    """
    MockMetadataProvider 内部专用表构造函数。

    Mock 允许：

        dwd_order_detail

    这种 bare synthetic identity。

    正式 AUTHORITATIVE Metadata
    后续由 Metadata Build Gate
    强制要求：

        project.table
    """

    normalized_full_name = (
        full_name
        .strip()
        .lower()
    )

    if "." in normalized_full_name:
        (
            project,
            table_name,
        ) = (
            normalized_full_name
            .rsplit(
                ".",
                1,
            )
        )
    else:
        project = ""
        table_name = (
            normalized_full_name
        )

    return TableMetadata(
        full_name=(
            normalized_full_name
        ),
        technical=(
            TableTechnicalMetadata(
                project=project,
                table_name=table_name,
                partition_fields=(
                    partition_fields
                ),
                column_count=(
                    len(columns)
                ),
            )
        ),
        business=(
            TableBusinessMetadata(
                description=(
                    description
                ),
            )
        ),
        operational=(
            TableOperationalMetadata()
        ),
        management=(
            TableManagementMetadata()
        ),
        columns=columns,
    )