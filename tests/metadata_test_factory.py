from __future__ import annotations

from collections.abc import (
    Mapping,
)

from dataclasses import (
    replace,
)

from sql_pilot_engine.metadata.models import (
    ColumnBusinessMetadata,
    ColumnManagementMetadata,
    ColumnMetadata,
    ColumnSemanticMetadata,
    ColumnTechnicalMetadata,
    TableBusinessMetadata,
    TableManagementMetadata,
    TableMetadata,
    TableOperationalMetadata,
    TableTechnicalMetadata,
)


def make_column_metadata(
    name: str,
    *,
    data_type: str = "string",
    nullable: bool | None = None,
    description: str = "",
    ordinal_position: int = 1,
    is_partition: bool = False,
) -> ColumnMetadata:
    """
    测试专用 ColumnMetadata Factory。

    只暴露现有测试最常使用的物理事实，
    其余新 Metadata 字段使用 Domain 默认值。

    不得被生产代码 import。
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


def make_table_metadata(
    full_name: str,
    *,
    columns: Mapping[
        str,
        ColumnMetadata,
    ] | None = None,
    partition_fields: tuple[
        str,
        ...,
    ] = (),
    description: str = "",
    row_count: int | None = None,
    size_bytes: int | None = None,
) -> TableMetadata:
    """
    测试专用 TableMetadata Factory。

    Qualified name：
        project.table

    Bare name：
        继续允许用于旧 Query Line 的 synthetic tests。

    正式 Runtime Metadata 是否允许 bare identity，
    由后续 Metadata Build Gate 控制，
    不由测试 Factory 定义。
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

    source_columns = dict(
        columns or {}
    )

    normalized_partitions = {
        name.strip().lower()
        for name
        in partition_fields
    }

    normalized_columns: dict[
        str,
        ColumnMetadata,
    ] = {}

    for (
        index,
        (name, column),
    ) in enumerate(
        source_columns.items(),
        start=1,
    ):
        normalized_name = (
            name.strip().lower()
        )

        technical = (
            column.technical
        )

        # 测试 Factory 自动保持：
        #
        # Table.partition_fields
        # 与
        # Column.is_partition
        #
        # 一致。
        if (
            normalized_name
            in normalized_partitions
            and not technical.is_partition
        ):
            technical = replace(
                technical,
                is_partition=True,
            )

        # 老测试通常没有显式关心
        # ordinal_position。
        #
        # Factory 在这里补出稳定顺序。
        if (
            technical
            .ordinal_position
            <= 0
        ):
            technical = replace(
                technical,
                ordinal_position=index,
            )

        normalized_columns[
            normalized_name
        ] = replace(
            column,
            technical=technical,
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
                    tuple(
                        field.strip().lower()
                        for field
                        in partition_fields
                    )
                ),
                column_count=(
                    len(
                        normalized_columns
                    )
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
            TableOperationalMetadata(
                row_count=row_count,
                size_bytes=size_bytes,
            )
        ),
        management=(
            TableManagementMetadata()
        ),
        columns=(
            normalized_columns
        ),
    )