from __future__ import annotations

import json
import sqlite3

from collections.abc import Iterable

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableMetadata,
)


def _json_text(
    values: Iterable[str],
) -> str:
    """
    将简单字符串集合编码成 SQLite TEXT。

    这里使用 JSON 的字段包括：

    - partition_fields
    - related_business
    - business_key

    这些数据：

    1. 属于当前对象自身；
    2. 一般整体加载；
    3. 当前没有强烈的反向查询需求。

    因此不单独拆关系表。
    """

    return json.dumps(
        list(values),
        ensure_ascii=False,
    )


def _nullable_bool(
    value: bool | None,
) -> int | None:
    """
    Python bool | None
        ↓
    SQLite INTEGER | NULL

    True  -> 1
    False -> 0
    None  -> NULL
    """

    if value is None:
        return None

    return int(value)


def _validate_table_for_write(
    table: TableMetadata,
) -> None:
    """
    校验跨 Metadata 子对象的一致性。

    注意：

    TableMetadata.__post_init__()
    负责单个 Domain Object 的基础 invariant。

    这里负责：

    technical table facts
        vs
    technical column facts

    之间的 cross-object consistency。
    """

    partition_fields = set(
        table
        .technical
        .partition_fields
    )

    partition_columns = {
        column.name
        for column
        in table.columns.values()
        if (
            column
            .technical
            .is_partition
        )
    }

    if (
        partition_fields
        != partition_columns
    ):
        raise ValueError(
            "Metadata partition definition "
            "is inconsistent for "
            f"{table.full_name!r}: "
            "table.partition_fields="
            f"{sorted(partition_fields)!r}, "
            "column.is_partition="
            f"{sorted(partition_columns)!r}"
        )

    ordinal_positions = [
        column
        .technical
        .ordinal_position
        for column
        in table.columns.values()
    ]

    if (
        len(ordinal_positions)
        != len(set(ordinal_positions))
    ):
        raise ValueError(
            "Duplicate column "
            "ordinal_position in "
            f"{table.full_name!r}."
        )

    upstream_tables = (
        table
        .technical
        .declared_upstream_tables
    )

    if (
        len(upstream_tables)
        != len(set(upstream_tables))
    ):
        raise ValueError(
            "Duplicate declared upstream "
            "table in "
            f"{table.full_name!r}."
        )


def write_metadata_tables(
    connection: sqlite3.Connection,
    tables: Iterable[TableMetadata],
) -> tuple[int, int]:
    """
    将已经标准化为 Agent3 Domain Contract 的
    Metadata 写入 SQLite Schema v3。

    本函数完全不关心：

    - Excel
    - Sheet 名
    - 外部列名
    - DataWorks API
    - 帆软导出格式

    它唯一接受：

        TableMetadata

    这就是 Persistence Boundary。
    """

    table_count = 0
    column_count = 0

    for table in tables:

        _validate_table_for_write(
            table
        )

        technical = (
            table.technical
        )

        business = (
            table.business
        )

        operational = (
            table.operational
        )

        management = (
            table.management
        )

        table_cursor = (
            connection.execute(
                """
                INSERT INTO metadata_table (
                    full_name,
                    project,
                    table_name,

                    code_path,
                    partition_fields_json,
                    column_count,
                    source_system,
                    processing_node,

                    description,
                    statistical_regime,
                    business_name,
                    related_business_json,
                    asset_category,
                    report_name,
                    purpose,
                    grain,
                    business_key_json,
                    owning_department,
                    data_origin,

                    data_cycle,
                    schedule_cycle,
                    update_mode,
                    data_period_field,
                    first_period,
                    latest_period,
                    period_note,
                    last_updated_at,
                    row_count,
                    size_bytes,

                    maintainer,
                    asset_status,
                    last_verified_at,
                    remark
                )
                VALUES (
                    ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    table.full_name,
                    technical.project,
                    technical.table_name,

                    technical.code_path,
                    _json_text(
                        technical
                        .partition_fields
                    ),
                    technical.column_count,
                    technical.source_system,
                    technical.processing_node,

                    business.description,
                    business.statistical_regime,
                    business.business_name,
                    _json_text(
                        business
                        .related_business
                    ),
                    business.asset_category,
                    business.report_name,
                    business.purpose,
                    business.grain,
                    _json_text(
                        business
                        .business_key
                    ),
                    business.owning_department,
                    business.data_origin,

                    operational.data_cycle,
                    operational.schedule_cycle,
                    operational.update_mode,
                    operational.data_period_field,
                    operational.first_period,
                    operational.latest_period,
                    operational.period_note,
                    operational.last_updated_at,
                    operational.row_count,
                    operational.size_bytes,

                    management.maintainer,
                    management.asset_status,
                    management.last_verified_at,
                    management.remark,
                ),
            )
        )

        table_id = int(
            table_cursor.lastrowid
        )

        table_count += 1

        # ----------------------------------------------
        # Declared Table Lineage
        # ----------------------------------------------

        for (
            ordinal_position,
            upstream_full_name,
        ) in enumerate(
            technical
            .declared_upstream_tables,
            start=1,
        ):
            connection.execute(
                """
                INSERT INTO metadata_table_upstream (
                    table_id,
                    upstream_full_name,
                    ordinal_position
                )
                VALUES (?, ?, ?)
                """,
                (
                    table_id,
                    upstream_full_name,
                    ordinal_position,
                ),
            )

        # ----------------------------------------------
        # Columns
        #
        # 明确按照 ordinal_position 写入，
        # 不依赖 Mapping 当前插入顺序。
        # ----------------------------------------------

        sorted_columns = sorted(
            table.columns.values(),
            key=lambda item: (
                item
                .technical
                .ordinal_position
            ),
        )

        for column in sorted_columns:

            column_cursor = (
                _write_column(
                    connection,
                    table_id=table_id,
                    column=column,
                )
            )

            column_id = int(
                column_cursor.lastrowid
            )

            column_count += 1

            for (
                upstream_position,
                upstream,
            ) in enumerate(
                column
                .technical
                .declared_upstream_columns,
                start=1,
            ):
                connection.execute(
                    """
                    INSERT INTO metadata_column_upstream (
                        column_id,
                        upstream_table_full_name,
                        upstream_column_name,
                        ordinal_position
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        column_id,
                        upstream.table_full_name,
                        upstream.column_name,
                        upstream_position,
                    ),
                )

    return (
        table_count,
        column_count,
    )


def _write_column(
    connection: sqlite3.Connection,
    *,
    table_id: int,
    column: ColumnMetadata,
) -> sqlite3.Cursor:
    """
    写入单个字段。

    单独抽出来的原因不是为了增加抽象，
    而是避免 write_metadata_tables()
    被字段 25+ 个列映射淹没。
    """

    technical = (
        column.technical
    )

    business = (
        column.business
    )

    semantic = (
        column.semantic
    )

    management = (
        column.management
    )

    return connection.execute(
        """
        INSERT INTO metadata_column (
            table_id,
            name,

            ordinal_position,
            data_type,
            nullable,
            is_partition,
            processing_kind,

            description,
            definition,
            collection_rule,
            validation_rule,
            processing_logic,
            data_format,
            unit,

            is_code_field,
            code_table_id,
            is_dimension,
            dimension_table,
            dimension_column,
            is_metric,
            metric_formula,
            metric_aggregation,

            lineage_source,
            lineage_confirmation_status,
            remark
        )
        VALUES (
            ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?
        )
        """,
        (
            table_id,
            column.name,

            technical.ordinal_position,
            technical.data_type,
            _nullable_bool(
                technical.nullable
            ),
            int(
                technical.is_partition
            ),
            technical.processing_kind,

            business.description,
            business.definition,
            business.collection_rule,
            business.validation_rule,
            business.processing_logic,
            business.data_format,
            business.unit,

            int(
                semantic.is_code_field
            ),
            semantic.code_table_id,
            int(
                semantic.is_dimension
            ),
            semantic.dimension_table,
            semantic.dimension_column,
            int(
                semantic.is_metric
            ),
            semantic.metric_formula,
            semantic.metric_aggregation,

            management.lineage_source,
            (
                management
                .lineage_confirmation_status
            ),
            management.remark,
        ),
    )