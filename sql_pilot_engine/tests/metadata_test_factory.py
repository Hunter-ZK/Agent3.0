from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

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
    data_type: str = "string",
    nullable: bool | None = None,
    description: str = "",
    distinct_count: int | None = None,
    *,
    ordinal_position: int = 1,
    is_partition: bool = False,
) -> ColumnMetadata:
    """测试专用 Builder；distinct_count 仅兼容旧测试输入，不进入新 Contract。"""

    _ = distinct_count
    return ColumnMetadata(
        name=name,
        technical=ColumnTechnicalMetadata(
            ordinal_position=ordinal_position,
            data_type=data_type,
            nullable=nullable,
            is_partition=is_partition,
        ),
        business=ColumnBusinessMetadata(description=description),
        semantic=ColumnSemanticMetadata(),
        management=ColumnManagementMetadata(),
    )


def make_table_metadata(
    full_name: str,
    columns: Mapping[str, ColumnMetadata],
    partition_fields: tuple[str, ...] = (),
    description: str = "",
    layer: str = "",
    row_count: int | None = None,
    size_bytes: int | None = None,
) -> TableMetadata:
    """测试专用 Builder；layer 仅兼容旧测试输入，不进入新 Contract。"""

    _ = layer
    normalized = full_name.strip().lower()
    if "." in normalized:
        project, table_name = normalized.rsplit(".", 1)
    else:
        project, table_name = "", normalized

    partitions = {item.strip().lower() for item in partition_fields}
    normalized_columns: dict[str, ColumnMetadata] = {}
    for index, (key, column) in enumerate(columns.items(), start=1):
        normalized_key = key.strip().lower()
        technical = column.technical
        desired_partition = normalized_key in partitions
        desired_ordinal = technical.ordinal_position
        if desired_ordinal <= 0 or (
            desired_ordinal == 1 and index > 1
        ):
            desired_ordinal = index
        if (
            technical.is_partition != desired_partition
            or technical.ordinal_position != desired_ordinal
        ):
            technical = replace(
                technical,
                ordinal_position=desired_ordinal,
                is_partition=desired_partition,
            )
            column = replace(column, technical=technical)
        normalized_columns[normalized_key] = column

    return TableMetadata(
        full_name=normalized,
        technical=TableTechnicalMetadata(
            project=project,
            table_name=table_name,
            partition_fields=tuple(partition_fields),
            column_count=len(normalized_columns),
        ),
        business=TableBusinessMetadata(description=description),
        operational=TableOperationalMetadata(
            row_count=row_count,
            size_bytes=size_bytes,
        ),
        management=TableManagementMetadata(),
        columns=normalized_columns,
    )
