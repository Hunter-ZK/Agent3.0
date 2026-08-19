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


class SQLiteMetadataRepository:
    """
    Metadata Runtime查询实现。

    只负责读取已经持久化好的SQLite Metadata DB。

    不负责：
    - 初始化数据库
    - 读取Excel
    - 导入数据
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
        以只读方式连接数据库。

        如果数据库不存在，直接报错，
        不允许Runtime偷偷创建一个空DB。
        """

        uri = (
            f"file:"
            f"{self._database_path.resolve()}"
            "?mode=ro"
        )
        print(f"{self._database_path.resolve()}")
        connection = sqlite3.connect(
            uri,
            uri=True,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        return connection

    @staticmethod
    def _active_batch_id(
        connection: sqlite3.Connection,
    ) -> int | None:

        row = connection.execute(
            """
            SELECT id
            FROM metadata_batch
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            return None

        return int(
            row["id"]
        )

    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:

        normalized = (
            full_name
            .strip()
            .lower()
        )

        names = [normalized]

        # SQL中可能有：
        # odps_project.table_name
        #
        # 当前Metadata只存table_name。
        if "." in normalized:
            names.append(
                normalized.rsplit(
                    ".",
                    1,
                )[-1]
            )

        try:
            with self._connect() as connection:

                batch_id = (
                    self._active_batch_id(
                        connection
                    )
                )

                if batch_id is None:
                    return (
                        TableLookupResult
                        .not_found()
                    )

                table_row = None

                for name in names:

                    table_row = (
                        connection.execute(
                            """
                            SELECT
                                id,
                                full_name,
                                description
                            FROM metadata_table
                            WHERE
                                batch_id = ?
                                AND full_name = ?
                            LIMIT 1
                            """,
                            (
                                batch_id,
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
                            is_partition
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
                            name=row["name"],

                            description=(
                                row["description"]
                                or ""
                            ),

                            data_type=(
                                row["data_type"]
                                or ""
                            ),

                            nullable=(
                                True
                                if row["nullable"]
                                is None
                                else bool(
                                    row["nullable"]
                                )
                            ),
                        )

                    for row
                    in column_rows
                }

                partition_fields = tuple(
                    row["name"]
                    for row
                    in column_rows
                    if row[
                        "is_partition"
                    ] == 1
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

    def find_tables(
        self,
        keyword: str,
        *,
        limit: int = 20,
    ) -> tuple[
        TableSearchResult,
        ...
    ]:

        query = keyword.strip()

        if not query:
            return ()

        with self._connect() as connection:

            batch_id = (
                self._active_batch_id(
                    connection
                )
            )

            if batch_id is None:
                return ()

            value = f"%{query}%"

            rows = connection.execute(
                """
                SELECT
                    full_name,
                    description,
                    layer
                FROM metadata_table
                WHERE
                    batch_id = ?
                    AND (
                        full_name LIKE ?
                        OR description LIKE ?
                    )
                ORDER BY full_name
                LIMIT ?
                """,
                (
                    batch_id,
                    value.lower(),
                    value,
                    limit,
                ),
            ).fetchall()

            return tuple(
                TableSearchResult(
                    full_name=(
                        row["full_name"]
                    ),

                    description=(
                        row["description"]
                        or ""
                    ),

                    layer=(
                        row["layer"]
                        or ""
                    ),
                )
                for row in rows
            )

    def find_columns(
        self,
        keyword: str,
        *,
        limit: int = 50,
    ) -> tuple[
        ColumnSearchResult,
        ...
    ]:

        query = keyword.strip()

        if not query:
            return ()

        with self._connect() as connection:

            batch_id = (
                self._active_batch_id(
                    connection
                )
            )

            if batch_id is None:
                return ()

            value = f"%{query}%"

            rows = connection.execute(
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
                    t.batch_id = ?
                    AND (
                        c.name LIKE ?
                        OR c.description LIKE ?
                    )

                ORDER BY
                    t.full_name,
                    c.name

                LIMIT ?
                """,
                (
                    batch_id,
                    value.lower(),
                    value,
                    limit,
                ),
            ).fetchall()

            return tuple(
                ColumnSearchResult(
                    table_full_name=(
                        row["full_name"]
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
                        row["data_type"]
                        or ""
                    ),
                )
                for row in rows
            )

    def find_column_usages(
        self,
        column_name: str,
        *,
        limit: int = 100,
    ) -> tuple[
        ColumnSearchResult,
        ...
    ]:

        normalized = (
            column_name
            .strip()
            .lower()
        )

        if not normalized:
            return ()

        with self._connect() as connection:

            batch_id = (
                self._active_batch_id(
                    connection
                )
            )

            if batch_id is None:
                return ()

            rows = connection.execute(
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
                    t.batch_id = ?
                    AND c.name = ?

                ORDER BY t.full_name

                LIMIT ?
                """,
                (
                    batch_id,
                    normalized,
                    limit,
                ),
            ).fetchall()

            return tuple(
                ColumnSearchResult(
                    table_full_name=(
                        row["full_name"]
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
                        row["data_type"]
                        or ""
                    ),
                )
                for row in rows
            )