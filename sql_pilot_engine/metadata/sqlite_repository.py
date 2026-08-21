from __future__ import annotations

import sqlite3

from pathlib import Path

from sql_pilot_engine.metadata.catalog import (
    ColumnSearchResult,
    TableSearchResult,
)

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableLookupResult,
    TableMetadata,
)

from sql_pilot_engine.metadata.schema import (
    METADATA_SCHEMA_VERSION,
)


def _fts_phrase(
    value: str,
) -> str:
    """
    将用户输入作为完整 FTS phrase，
    避免 AND / OR / NOT 等字符串
    被解释成 FTS 查询语法。
    """

    escaped = value.replace(
        '"',
        '""',
    )

    return f'"{escaped}"'


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
    - Standards Import
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
        Runtime 必须以只读方式打开事实库。

        如果：
        - DB 不存在；
        - DB 未完成 Build；
        - Schema Version 不一致；

        直接报错。

        Runtime 不进行 Migration。
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
                SELECT schema_version
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

        names = [
            normalized
        ]

        # SQL 可能出现：
        # project.table_name
        #
        # 当前 Metadata Source
        # 可能只保存 table_name。
        if "." in normalized:

            base_name = (
                normalized
                .rsplit(
                    ".",
                    1,
                )[-1]
            )

            if base_name not in names:
                names.append(
                    base_name
                )

        try:
            with self._connect() as connection:

                table_row = None

                for name in names:

                    table_row = (
                        connection.execute(
                            """
                            SELECT
                                id,
                                full_name,
                                description,
                                layer,
                                row_count,
                                size_bytes
                            FROM metadata_table
                            WHERE full_name = ?
                            LIMIT 1
                            """,
                            (
                                name,
                            ),
                        )
                        .fetchone()
                    )

                    if table_row is not None:
                        break

                if table_row is None:

                    return (
                        TableLookupResult
                        .not_found()
                    )

                column_rows = (
                    connection.execute(
                        """
                        SELECT
                            name,
                            description,
                            data_type,
                            nullable,
                            ordinal_position,
                            is_partition,
                            distinct_count
                        FROM metadata_column
                        WHERE table_id = ?
                        ORDER BY
                            ordinal_position,
                            id
                        """,
                        (
                            table_row["id"],
                        ),
                    )
                    .fetchall()
                )

                columns = {
                    row["name"]:
                        ColumnMetadata(
                            name=(
                                row["name"]
                            ),

                            description=(
                                row["description"]
                                or ""
                            ),

                            data_type=(
                                row["data_type"]
                                or ""
                            ),

                            nullable=(
                                None
                                if row["nullable"]
                                is None
                                else bool(
                                    row[
                                        "nullable"
                                    ]
                                )
                            ),

                            distinct_count=(
                                row[
                                    "distinct_count"
                                ]
                            ),
                        )

                    for row in column_rows
                }

                partition_fields = tuple(
                    row["name"]

                    for row in column_rows

                    if (
                        row[
                            "is_partition"
                        ]
                        == 1
                    )
                )

                return (
                    TableLookupResult
                    .found(
                        TableMetadata(
                            full_name=(
                                table_row[
                                    "full_name"
                                ]
                            ),

                            description=(
                                table_row[
                                    "description"
                                ]
                                or ""
                            ),

                            layer=(
                                table_row[
                                    "layer"
                                ]
                                or ""
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

                            columns=columns,

                            partition_fields=(
                                partition_fields
                            ),
                        )
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
        ...
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

            # ------------------------------------------------
            # 1. Exact Identifier 优先
            # ------------------------------------------------

            exact_rows = (
                connection.execute(
                    """
                    SELECT
                        full_name,
                        description,
                        layer
                    FROM metadata_table
                    WHERE full_name = ?
                    """,
                    (
                        query,
                    ),
                )
                .fetchall()
            )

            for row in exact_rows:

                name = row[
                    "full_name"
                ]

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

                        layer=(
                            row[
                                "layer"
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

            # ------------------------------------------------
            # 2. <3 字符：LIKE fallback
            # ------------------------------------------------

            if len(query) < 3:

                value = (
                    f"%{query}%"
                )

                rows = (
                    connection.execute(
                        """
                        SELECT
                            full_name,
                            description,
                            layer
                        FROM metadata_table
                        WHERE
                            full_name LIKE ?
                            OR description LIKE ?
                        ORDER BY full_name
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

            # ------------------------------------------------
            # 3. >=3 字符：FTS5 trigram
            # ------------------------------------------------

            else:

                rows = (
                    connection.execute(
                        """
                        SELECT
                            t.full_name,
                            t.description,
                            t.layer
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
                    row["full_name"]
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

                        layer=(
                            row[
                                "layer"
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

            return tuple(results)

    def find_columns(
        self,
        keyword: str,
        *,
        limit: int = 50,
    ) -> tuple[
        ColumnSearchResult,
        ...
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

            # ------------------------------------------------
            # 1. Exact column identifier
            # ------------------------------------------------

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
                    row["name"],
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

            # ------------------------------------------------
            # 2. Short query fallback
            # ------------------------------------------------

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
                    row["name"],
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

            return tuple(results)

    def find_column_usages(
        self,
        column_name: str,
    ) -> tuple[
        ColumnSearchResult,
        ...
    ]:
        """
        Exact Fact Query。

        不使用 limit，
        必须返回所有物理使用位置。
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

                for row in rows
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
                row["name"]
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

    @staticmethod
    def _normalize_table_lookup_name(
        table_name: str,
    ) -> str:
        """
        将 Runtime SQL 中的物理表标识
        转换为当前 Metadata V1 的表名口径。

        当前 Metadata DB 以裸物理表名作为身份：

            odps_prd_dwd.ods_hd_100_cldkxx
            -> ods_hd_100_cldkxx

        同时兼容反引号等 SQL 标识符包装。
        """

        normalized = (
            table_name
            .strip()
            .replace("`", "")
            .replace('"', "")
        )

        if not normalized:
            return ""

        return (
            normalized
            .split(".")[-1]
            .strip()
            .lower()
        )