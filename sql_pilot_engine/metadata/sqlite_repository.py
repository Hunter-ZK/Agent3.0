from __future__ import annotations

import json
import sqlite3

from pathlib import Path

from sql_pilot_engine.metadata.catalog import (
    ColumnSearchResult,
    TableSearchResult,
)

from sql_pilot_engine.metadata.models import (
    ColumnBusinessMetadata,
    ColumnManagementMetadata,
    ColumnMetadata,
    ColumnSemanticMetadata,
    ColumnTechnicalMetadata,
    PhysicalColumnRef,
    TableBusinessMetadata,
    TableLookupResult,
    TableManagementMetadata,
    TableMetadata,
    TableOperationalMetadata,
    TableTechnicalMetadata,
)

from sql_pilot_engine.metadata.schema import (
    METADATA_SCHEMA_VERSION,
)


def _fts_phrase(
    value: str,
) -> str:
    """
    将查询内容转成完整 FTS phrase。

    防止 AND / OR / NOT 等普通字符串
    被 SQLite FTS 当成查询语法。
    """

    escaped = value.replace(
        '"',
        '""',
    )

    return f'"{escaped}"'


def _decode_text_tuple(
    raw_value: str | None,
) -> tuple[str, ...]:
    """
    解码普通业务文本数组。

    不主动 lowercase，
    避免修改业务名称等原始文本。
    """

    if not raw_value:
        return ()

    value = json.loads(
        raw_value
    )

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            "Metadata JSON value "
            "must be a list."
        )

    return tuple(
        str(item).strip()
        for item
        in value
        if str(item).strip()
    )


def _decode_identifier_tuple(
    raw_value: str | None,
) -> tuple[str, ...]:
    """
    解码物理标识符数组。

    字段名 / 分区字段等 canonical identifier
    统一 lowercase。
    """

    return tuple(
        item.lower()
        for item
        in _decode_text_tuple(
            raw_value
        )
    )


def _optional_bool(
    value: object,
) -> bool | None:
    if value is None:
        return None

    return bool(
        int(value)
    )


class SQLiteMetadataRepository:
    """
    Metadata Runtime 只读 Repository。

    同时实现：

    - MetadataProvider
    - MetadataCatalog

    不负责：

    - Schema Init
    - Excel Import
    - Database Rebuild
    - Schema Migration

    Runtime 永远只读正式构建完成的 metadata.db。
    """

    def __init__(
        self,
        database_path: str | Path,
    ) -> None:

        self._database_path = Path(
            database_path
        )

    def _connect(
        self,
    ) -> sqlite3.Connection:
        """
        以 SQLite read-only mode 打开事实库。

        Runtime 不执行 migration。

        DB 不存在、Build 未完成、
        Schema Version 不一致均直接报错。
        """

        uri = (
            "file:"
            f"{self._database_path.resolve()}"
            "?mode=ro"
        )

        connection = sqlite3.connect(
            uri,
            uri=True,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        try:
            row = connection.execute(
                """
                SELECT
                    schema_version
                FROM metadata_build_info
                WHERE id = 1
                """
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "metadata.db has no "
                    "completed build info. "
                    "Run full metadata rebuild."
                )

            actual_version = int(
                row["schema_version"]
            )

            if (
                actual_version
                != METADATA_SCHEMA_VERSION
            ):
                raise RuntimeError(
                    "Unsupported metadata.db "
                    "schema version: "
                    f"{actual_version}; "
                    "expected "
                    f"{METADATA_SCHEMA_VERSION}. "
                    "Run full metadata rebuild."
                )

            return connection

        except Exception:
            connection.close()
            raise

    # ======================================================
    # MetadataProvider
    # ======================================================

    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:

        normalized = (
            full_name
            .strip()
            .lower()
        )

        if not normalized:
            return (
                TableLookupResult
                .not_found()
            )

        try:
            with self._connect() as connection:

                table_row = (
                    connection.execute(
                        """
                        SELECT
                            *
                        FROM metadata_table
                        WHERE full_name = ?
                        LIMIT 1
                        """,
                        (
                            normalized,
                        ),
                    )
                    .fetchone()
                )

                if table_row is None:
                    return (
                        TableLookupResult
                        .not_found()
                    )

                table_id = int(
                    table_row["id"]
                )

                upstream_table_rows = (
                    connection.execute(
                        """
                        SELECT
                            upstream_full_name
                        FROM metadata_table_upstream
                        WHERE table_id = ?
                        ORDER BY
                            ordinal_position
                        """,
                        (
                            table_id,
                        ),
                    )
                    .fetchall()
                )

                declared_upstream_tables = tuple(
                    row[
                        "upstream_full_name"
                    ]
                    for row
                    in upstream_table_rows
                )

                column_rows = (
                    connection.execute(
                        """
                        SELECT
                            *
                        FROM metadata_column
                        WHERE table_id = ?
                        ORDER BY
                            ordinal_position,
                            id
                        """,
                        (
                            table_id,
                        ),
                    )
                    .fetchall()
                )

                column_upstream_rows = (
                    connection.execute(
                        """
                        SELECT
                            column_id,
                            upstream_table_full_name,
                            upstream_column_name
                        FROM metadata_column_upstream
                        WHERE column_id IN (
                            SELECT id
                            FROM metadata_column
                            WHERE table_id = ?
                        )
                        ORDER BY
                            column_id,
                            ordinal_position
                        """,
                        (
                            table_id,
                        ),
                    )
                    .fetchall()
                )

                upstream_by_column: dict[
                    int,
                    list[
                        PhysicalColumnRef
                    ],
                ] = {}

                for row in column_upstream_rows:

                    column_id = int(
                        row["column_id"]
                    )

                    upstream_by_column.setdefault(
                        column_id,
                        [],
                    ).append(
                        PhysicalColumnRef(
                            table_full_name=(
                                row[
                                    "upstream_table_full_name"
                                ]
                            ),
                            column_name=(
                                row[
                                    "upstream_column_name"
                                ]
                            ),
                        )
                    )

                columns: dict[
                    str,
                    ColumnMetadata,
                ] = {}

                for row in column_rows:

                    column_id = int(
                        row["id"]
                    )

                    column = ColumnMetadata(
                        name=(
                            row["name"]
                        ),

                        technical=(
                            ColumnTechnicalMetadata(
                                ordinal_position=(
                                    int(
                                        row[
                                            "ordinal_position"
                                        ]
                                    )
                                ),

                                data_type=(
                                    row[
                                        "data_type"
                                    ]
                                    or ""
                                ),

                                nullable=(
                                    _optional_bool(
                                        row[
                                            "nullable"
                                        ]
                                    )
                                ),

                                is_partition=(
                                    bool(
                                        row[
                                            "is_partition"
                                        ]
                                    )
                                ),

                                declared_upstream_columns=(
                                    tuple(
                                        upstream_by_column
                                        .get(
                                            column_id,
                                            [],
                                        )
                                    )
                                ),

                                processing_kind=(
                                    row[
                                        "processing_kind"
                                    ]
                                ),
                            )
                        ),

                        business=(
                            ColumnBusinessMetadata(
                                description=(
                                    row[
                                        "description"
                                    ]
                                    or ""
                                ),

                                definition=(
                                    row[
                                        "definition"
                                    ]
                                ),

                                collection_rule=(
                                    row[
                                        "collection_rule"
                                    ]
                                ),

                                validation_rule=(
                                    row[
                                        "validation_rule"
                                    ]
                                ),

                                processing_logic=(
                                    row[
                                        "processing_logic"
                                    ]
                                ),

                                data_format=(
                                    row[
                                        "data_format"
                                    ]
                                ),

                                unit=(
                                    row["unit"]
                                ),
                            )
                        ),

                        semantic=(
                            ColumnSemanticMetadata(
                                is_code_field=(
                                    bool(
                                        row[
                                            "is_code_field"
                                        ]
                                    )
                                ),

                                code_table_id=(
                                    row[
                                        "code_table_id"
                                    ]
                                ),

                                is_dimension=(
                                    bool(
                                        row[
                                            "is_dimension"
                                        ]
                                    )
                                ),

                                dimension_table=(
                                    row[
                                        "dimension_table"
                                    ]
                                ),

                                dimension_column=(
                                    row[
                                        "dimension_column"
                                    ]
                                ),

                                is_metric=(
                                    bool(
                                        row[
                                            "is_metric"
                                        ]
                                    )
                                ),

                                metric_formula=(
                                    row[
                                        "metric_formula"
                                    ]
                                ),

                                metric_aggregation=(
                                    row[
                                        "metric_aggregation"
                                    ]
                                ),
                            )
                        ),

                        management=(
                            ColumnManagementMetadata(
                                lineage_source=(
                                    row[
                                        "lineage_source"
                                    ]
                                ),

                                lineage_confirmation_status=(
                                    row[
                                        "lineage_confirmation_status"
                                    ]
                                ),

                                remark=(
                                    row["remark"]
                                ),
                            )
                        ),
                    )

                    columns[
                        column.name
                    ] = column

                table = TableMetadata(
                    full_name=(
                        table_row[
                            "full_name"
                        ]
                    ),

                    technical=(
                        TableTechnicalMetadata(
                            project=(
                                table_row[
                                    "project"
                                ]
                                or ""
                            ),

                            table_name=(
                                table_row[
                                    "table_name"
                                ]
                            ),

                            code_path=(
                                table_row[
                                    "code_path"
                                ]
                            ),

                            partition_fields=(
                                _decode_identifier_tuple(
                                    table_row[
                                        "partition_fields_json"
                                    ]
                                )
                            ),

                            column_count=(
                                int(
                                    table_row[
                                        "column_count"
                                    ]
                                )
                            ),

                            source_system=(
                                table_row[
                                    "source_system"
                                ]
                            ),

                            declared_upstream_tables=(
                                declared_upstream_tables
                            ),

                            processing_node=(
                                table_row[
                                    "processing_node"
                                ]
                            ),
                        )
                    ),

                    business=(
                        TableBusinessMetadata(
                            description=(
                                table_row[
                                    "description"
                                ]
                                or ""
                            ),

                            statistical_regime=(
                                table_row[
                                    "statistical_regime"
                                ]
                            ),

                            business_name=(
                                table_row[
                                    "business_name"
                                ]
                            ),

                            related_business=(
                                _decode_text_tuple(
                                    table_row[
                                        "related_business_json"
                                    ]
                                )
                            ),

                            asset_category=(
                                table_row[
                                    "asset_category"
                                ]
                            ),

                            report_name=(
                                table_row[
                                    "report_name"
                                ]
                            ),

                            purpose=(
                                table_row[
                                    "purpose"
                                ]
                            ),

                            grain=(
                                table_row[
                                    "grain"
                                ]
                            ),

                            business_key=(
                                _decode_identifier_tuple(
                                    table_row[
                                        "business_key_json"
                                    ]
                                )
                            ),

                            owning_department=(
                                table_row[
                                    "owning_department"
                                ]
                            ),

                            data_origin=(
                                table_row[
                                    "data_origin"
                                ]
                            ),
                        )
                    ),

                    operational=(
                        TableOperationalMetadata(
                            data_cycle=(
                                table_row[
                                    "data_cycle"
                                ]
                            ),

                            schedule_cycle=(
                                table_row[
                                    "schedule_cycle"
                                ]
                            ),

                            update_mode=(
                                table_row[
                                    "update_mode"
                                ]
                            ),

                            data_period_field=(
                                table_row[
                                    "data_period_field"
                                ]
                            ),

                            first_period=(
                                table_row[
                                    "first_period"
                                ]
                            ),

                            latest_period=(
                                table_row[
                                    "latest_period"
                                ]
                            ),

                            period_note=(
                                table_row[
                                    "period_note"
                                ]
                            ),

                            last_updated_at=(
                                table_row[
                                    "last_updated_at"
                                ]
                            ),

                            row_count=(
                                table_row[
                                    "row_count"
                                ]
                            ),

                            size_bytes=(
                                table_row[
                                    "size_bytes"
                                ]
                            ),
                        )
                    ),

                    management=(
                        TableManagementMetadata(
                            maintainer=(
                                table_row[
                                    "maintainer"
                                ]
                            ),

                            asset_status=(
                                table_row[
                                    "asset_status"
                                ]
                            ),

                            last_verified_at=(
                                table_row[
                                    "last_verified_at"
                                ]
                            ),

                            remark=(
                                table_row[
                                    "remark"
                                ]
                            ),
                        )
                    ),

                    columns=columns,
                )

                return (
                    TableLookupResult
                    .found(
                        table
                    )
                )

        except Exception as exc:
            return (
                TableLookupResult
                .failed(
                    str(exc)
                )
            )

    # ======================================================
    # MetadataCatalog
    # ======================================================

    def find_tables(
        self,
        keyword: str,
        *,
        limit: int = 20,
    ) -> tuple[
        TableSearchResult,
        ...,
    ]:

        query = (
            keyword
            .strip()
            .lower()
        )

        if (
            not query
            or limit <= 0
        ):
            return ()

        with self._connect() as connection:

            results: list[
                TableSearchResult
            ] = []

            seen: set[str] = set()

            exact_rows = (
                connection.execute(
                    """
                    SELECT
                        full_name,
                        description
                    FROM metadata_table
                    WHERE
                        full_name = ?
                        OR table_name = ?
                    ORDER BY full_name
                    LIMIT ?
                    """,
                    (
                        query,
                        query,
                        limit,
                    ),
                )
                .fetchall()
            )

            for row in exact_rows:

                name = (
                    row[
                        "full_name"
                    ]
                )

                if name in seen:
                    continue

                seen.add(name)

                results.append(
                    TableSearchResult(
                        full_name=name,
                        description=(
                            row[
                                "description"
                            ]
                            or ""
                        ),
                    )
                )

            remaining = (
                limit
                - len(results)
            )

            if remaining <= 0:
                return tuple(
                    results[:limit]
                )

            if len(query) < 3:

                value = (
                    f"%{query}%"
                )

                rows = (
                    connection.execute(
                        """
                        SELECT
                            full_name,
                            description
                        FROM metadata_table
                        WHERE
                            full_name LIKE ?
                            OR table_name LIKE ?
                            OR description LIKE ?
                        ORDER BY full_name
                        LIMIT ?
                        """,
                        (
                            value,
                            value,
                            value,
                            remaining * 2,
                        ),
                    )
                    .fetchall()
                )

            else:

                rows = (
                    connection.execute(
                        """
                        SELECT
                            t.full_name,
                            t.description
                        FROM metadata_table_fts
                        JOIN metadata_table t
                            ON t.id =
                               metadata_table_fts.rowid
                        WHERE
                            metadata_table_fts
                            MATCH ?
                        ORDER BY
                            bm25(
                                metadata_table_fts
                            ),
                            t.full_name
                        LIMIT ?
                        """,
                        (
                            _fts_phrase(
                                query
                            ),
                            remaining * 2,
                        ),
                    )
                    .fetchall()
                )

            for row in rows:

                name = (
                    row[
                        "full_name"
                    ]
                )

                if name in seen:
                    continue

                seen.add(name)

                results.append(
                    TableSearchResult(
                        full_name=name,
                        description=(
                            row[
                                "description"
                            ]
                            or ""
                        ),
                    )
                )

                if (
                    len(results)
                    >= limit
                ):
                    break

            return tuple(
                results
            )

    def find_table_identifiers(
        self,
        table_name: str,
    ) -> tuple[
        TableSearchResult,
        ...,
    ]:
        """
        Complete Fact Query。

        qualified:
            project.loan_detail

        只匹配 full_name。

        bare:
            loan_detail

        返回所有 table_name 精确等于
        loan_detail 的 canonical candidates。

        不做：
        - fuzzy
        - FTS
        - Top-N
        """

        normalized = (
            table_name
            .strip()
            .lower()
        )

        if not normalized:
            return ()

        with self._connect() as connection:

            rows = (
                connection.execute(
                    """
                    SELECT
                        full_name,
                        description
                    FROM metadata_table
                    WHERE
                        full_name = ?
                        OR table_name = ?
                    ORDER BY
                        full_name
                    """,
                    (
                        normalized,
                        normalized,
                    ),
                )
                .fetchall()
            )

            return tuple(
                TableSearchResult(
                    full_name=(
                        row[
                            "full_name"
                        ]
                    ),
                    description=(
                        row[
                            "description"
                        ]
                        or ""
                    ),
                )
                for row
                in rows
            )

    def find_columns(
        self,
        keyword: str,
        *,
        limit: int = 50,
    ) -> tuple[
        ColumnSearchResult,
        ...,
    ]:

        query = (
            keyword
            .strip()
            .lower()
        )

        if (
            not query
            or limit <= 0
        ):
            return ()

        with self._connect() as connection:

            results: list[
                ColumnSearchResult
            ] = []

            seen: set[
                tuple[str, str]
            ] = set()

            exact_rows = (
                connection.execute(
                    """
                    SELECT
                        t.full_name,

                        t.description
                            AS table_description,

                        c.name,

                        c.description
                            AS column_description,

                        c.data_type

                    FROM metadata_column c

                    JOIN metadata_table t
                        ON t.id = c.table_id

                    WHERE c.name = ?

                    ORDER BY
                        t.full_name,
                        c.name

                    LIMIT ?
                    """,
                    (
                        query,
                        limit,
                    ),
                )
                .fetchall()
            )

            for row in exact_rows:

                key = (
                    row[
                        "full_name"
                    ],
                    row[
                        "name"
                    ],
                )

                seen.add(key)

                results.append(
                    self._column_result(
                        row
                    )
                )

            remaining = (
                limit
                - len(results)
            )

            if remaining <= 0:
                return tuple(
                    results[:limit]
                )

            if len(query) < 3:

                value = (
                    f"%{query}%"
                )

                rows = (
                    connection.execute(
                        """
                        SELECT
                            t.full_name,

                            t.description
                                AS table_description,

                            c.name,

                            c.description
                                AS column_description,

                            c.data_type

                        FROM metadata_column c

                        JOIN metadata_table t
                            ON t.id = c.table_id

                        WHERE
                            c.name LIKE ?
                            OR c.description LIKE ?

                        ORDER BY
                            t.full_name,
                            c.name

                        LIMIT ?
                        """,
                        (
                            value,
                            value,
                            remaining * 2,
                        ),
                    )
                    .fetchall()
                )

            else:

                rows = (
                    connection.execute(
                        """
                        SELECT
                            t.full_name,

                            t.description
                                AS table_description,

                            c.name,

                            c.description
                                AS column_description,

                            c.data_type

                        FROM metadata_column_fts

                        JOIN metadata_column c
                            ON c.id =
                               metadata_column_fts.rowid

                        JOIN metadata_table t
                            ON t.id =
                               c.table_id

                        WHERE
                            metadata_column_fts
                            MATCH ?

                        ORDER BY
                            bm25(
                                metadata_column_fts
                            ),
                            t.full_name,
                            c.name

                        LIMIT ?
                        """,
                        (
                            _fts_phrase(
                                query
                            ),
                            remaining * 2,
                        ),
                    )
                    .fetchall()
                )

            for row in rows:

                key = (
                    row[
                        "full_name"
                    ],
                    row[
                        "name"
                    ],
                )

                if key in seen:
                    continue

                seen.add(key)

                results.append(
                    self._column_result(
                        row
                    )
                )

                if (
                    len(results)
                    >= limit
                ):
                    break

            return tuple(
                results
            )

    def find_column_usages(
        self,
        column_name: str,
    ) -> tuple[
        ColumnSearchResult,
        ...,
    ]:
        """
        Complete Fact Query。

        不使用 Top-N，
        返回全部精确字段使用位置。
        """

        normalized = (
            column_name
            .strip()
            .lower()
        )

        if not normalized:
            return ()

        with self._connect() as connection:

            rows = (
                connection.execute(
                    """
                    SELECT
                        t.full_name,

                        t.description
                            AS table_description,

                        c.name,

                        c.description
                            AS column_description,

                        c.data_type

                    FROM metadata_column c

                    JOIN metadata_table t
                        ON t.id = c.table_id

                    WHERE c.name = ?

                    ORDER BY
                        t.full_name
                    """,
                    (
                        normalized,
                    ),
                )
                .fetchall()
            )

            return tuple(
                self._column_result(
                    row
                )
                for row
                in rows
            )

    @staticmethod
    def _column_result(
        row: sqlite3.Row,
    ) -> ColumnSearchResult:

        return ColumnSearchResult(
            table_full_name=(
                row[
                    "full_name"
                ]
            ),

            table_description=(
                row[
                    "table_description"
                ]
                or ""
            ),

            column_name=(
                row[
                    "name"
                ]
            ),

            column_description=(
                row[
                    "column_description"
                ]
                or ""
            ),

            data_type=(
                row[
                    "data_type"
                ]
                or ""
            ),
        )