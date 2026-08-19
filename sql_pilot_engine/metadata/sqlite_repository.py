from __future__ import annotations

import sqlite3

from pathlib import Path

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    MetadataColumnMatch,
    MetadataSnapshot,
    MetadataTableMatch,
    TableLookupResult,
    TableMetadata,
)


class SQLiteMetadataRepository:
    """
    Shared Metadata V0.1的SQLite实现。

    SQLite负责：
    - 元数据快照存储
    - 精确表查询
    - 简单资产发现
    - 字段复用查询

    它同时满足MetadataProvider.get_table契约，
    因此可以直接供现有SQL Validation使用。
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

        self._database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        connection = sqlite3.connect(
            self._database_path
        )

        connection.row_factory = (
            sqlite3.Row
        )

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        return connection

    def initialize(
        self,
    ) -> None:

        with self._connect() as connection:

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata_batch (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    snapshot_label TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER NOT NULL
                        DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS metadata_table (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL,
                    full_name TEXT NOT NULL,
                    layer TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (batch_id)
                        REFERENCES metadata_batch(id)
                        ON DELETE CASCADE,
                    UNIQUE (batch_id, full_name)
                );

                CREATE TABLE IF NOT EXISTS
                metadata_table_description (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_id INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    is_primary INTEGER NOT NULL
                        DEFAULT 0,
                    FOREIGN KEY (table_id)
                        REFERENCES metadata_table(id)
                        ON DELETE CASCADE,
                    UNIQUE (table_id, description)
                );

                CREATE TABLE IF NOT EXISTS metadata_column (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    data_type TEXT NOT NULL DEFAULT '',
                    nullable INTEGER,
                    ordinal_position INTEGER,
                    is_partition INTEGER,
                    FOREIGN KEY (table_id)
                        REFERENCES metadata_table(id)
                        ON DELETE CASCADE,
                    UNIQUE (table_id, name)
                );

                CREATE TABLE IF NOT EXISTS
                metadata_column_description (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    column_id INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    is_primary INTEGER NOT NULL
                        DEFAULT 0,
                    FOREIGN KEY (column_id)
                        REFERENCES metadata_column(id)
                        ON DELETE CASCADE,
                    UNIQUE (column_id, description)
                );

                CREATE INDEX IF NOT EXISTS
                idx_metadata_table_name
                ON metadata_table(full_name);

                CREATE INDEX IF NOT EXISTS
                idx_metadata_column_name
                ON metadata_column(name);

                CREATE INDEX IF NOT EXISTS
                idx_table_description
                ON metadata_table_description(description);

                CREATE INDEX IF NOT EXISTS
                idx_column_description
                ON metadata_column_description(description);
                """
            )

    def import_snapshot(
        self,
        snapshot: MetadataSnapshot,
        *,
        activate: bool = True,
    ) -> int:

        with self._connect() as connection:

            cursor = connection.execute(
                """
                INSERT INTO metadata_batch (
                    source_name,
                    snapshot_label,
                    is_active
                )
                VALUES (?, ?, 0)
                """,
                (
                    snapshot.source_name,
                    snapshot.snapshot_label,
                ),
            )

            batch_id = int(
                cursor.lastrowid
            )

            for table in snapshot.tables:

                table_cursor = (
                    connection.execute(
                        """
                        INSERT INTO metadata_table (
                            batch_id,
                            full_name,
                            layer
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            batch_id,
                            table.full_name
                            .strip()
                            .lower(),
                            table.layer
                            .strip()
                            .lower(),
                        ),
                    )
                )

                table_id = int(
                    table_cursor.lastrowid
                )

                for index, description in enumerate(
                    table.descriptions
                ):
                    if not description.strip():
                        continue

                    connection.execute(
                        """
                        INSERT OR IGNORE INTO
                        metadata_table_description (
                            table_id,
                            description,
                            is_primary
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            table_id,
                            description.strip(),
                            1 if index == 0 else 0,
                        ),
                    )

                for column in table.columns:

                    column_cursor = (
                        connection.execute(
                            """
                            INSERT INTO metadata_column (
                                table_id,
                                name,
                                data_type,
                                nullable,
                                ordinal_position,
                                is_partition
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                table_id,
                                column.name
                                .strip()
                                .lower(),

                                column.data_type
                                .strip(),

                                (
                                    None
                                    if column.nullable
                                    is None
                                    else int(
                                        column.nullable
                                    )
                                ),

                                column.ordinal_position,

                                (
                                    None
                                    if column.is_partition
                                    is None
                                    else int(
                                        column.is_partition
                                    )
                                ),
                            ),
                        )
                    )

                    column_id = int(
                        column_cursor.lastrowid
                    )

                    for (
                        description_index,
                        description,
                    ) in enumerate(
                        column.descriptions
                    ):
                        if not description.strip():
                            continue

                        connection.execute(
                            """
                            INSERT OR IGNORE INTO
                            metadata_column_description (
                                column_id,
                                description,
                                is_primary
                            )
                            VALUES (?, ?, ?)
                            """,
                            (
                                column_id,
                                description.strip(),

                                (
                                    1
                                    if description_index
                                    == 0
                                    else 0
                                ),
                            ),
                        )

            if activate:

                connection.execute(
                    """
                    UPDATE metadata_batch
                    SET is_active = 0
                    """
                )

                connection.execute(
                    """
                    UPDATE metadata_batch
                    SET is_active = 1
                    WHERE id = ?
                    """,
                    (batch_id,),
                )

            return batch_id

    def _active_batch_id(
        self,
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

        return int(row["id"])

    def _find_table_row(
        self,
        connection: sqlite3.Connection,
        *,
        batch_id: int,
        full_name: str,
    ) -> sqlite3.Row | None:

        normalized = (
            full_name.strip().lower()
        )

        candidates = [normalized]

        # SQL中经常出现：
        # project.table
        #
        # 当前Excel只保存table，
        # 因此精确查询失败时允许尝试basename。
        if "." in normalized:
            candidates.append(
                normalized.rsplit(
                    ".",
                    1,
                )[-1]
            )

        for candidate in candidates:

            row = connection.execute(
                """
                SELECT
                    t.id,
                    t.full_name,
                    t.layer,
                    COALESCE(
                        (
                            SELECT description
                            FROM metadata_table_description td
                            WHERE td.table_id = t.id
                            ORDER BY
                                td.is_primary DESC,
                                td.id ASC
                            LIMIT 1
                        ),
                        ''
                    ) AS description
                FROM metadata_table t
                WHERE
                    t.batch_id = ?
                    AND t.full_name = ?
                LIMIT 1
                """,
                (
                    batch_id,
                    candidate,
                ),
            ).fetchone()

            if row is not None:
                return row

        return None

    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:

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

                table_row = (
                    self._find_table_row(
                        connection,
                        batch_id=batch_id,
                        full_name=full_name,
                    )
                )

                if table_row is None:
                    return (
                        TableLookupResult
                        .not_found()
                    )

                column_rows = (
                    connection.execute(
                        """
                        SELECT
                            c.name,
                            c.data_type,
                            c.nullable,
                            c.is_partition,
                            COALESCE(
                                (
                                    SELECT description
                                    FROM
                                    metadata_column_description cd
                                    WHERE
                                        cd.column_id = c.id
                                    ORDER BY
                                        cd.is_primary DESC,
                                        cd.id ASC
                                    LIMIT 1
                                ),
                                ''
                            ) AS description
                        FROM metadata_column c
                        WHERE c.table_id = ?
                        ORDER BY
                            COALESCE(
                                c.ordinal_position,
                                2147483647
                            ),
                            c.id
                        """,
                        (
                            table_row["id"],
                        ),
                    ).fetchall()
                )

                columns = {
                    row["name"]: ColumnMetadata(
                        name=row["name"],

                        data_type=(
                            row["data_type"]
                            or ""
                        ),

                        # 当前旧DTO只能表达bool。
                        # 如果原始元数据未知，
                        # 暂时按True返回。
                        # Validation V1目前主要使用
                        # 表/字段存在性，不依赖nullable。
                        nullable=(
                            True
                            if row["nullable"]
                            is None
                            else bool(
                                row["nullable"]
                            )
                        ),

                        description=(
                            row["description"]
                            or ""
                        ),
                    )
                    for row
                    in column_rows
                }

                partition_fields = tuple(
                    row["name"]
                    for row in column_rows
                    if row["is_partition"] == 1
                )

                table = TableMetadata(
                    full_name=(
                        table_row[
                            "full_name"
                        ]
                    ),

                    columns=columns,

                    partition_fields=(
                        partition_fields
                    ),

                    description=(
                        table_row[
                            "description"
                        ]
                        or ""
                    ),
                )

                return (
                    TableLookupResult
                    .found(table)
                )

        except Exception as exc:

            return (
                TableLookupResult.failed(
                    str(exc)
                )
            )

    def find_tables(
        self,
        keyword: str,
        *,
        limit: int = 20,
    ) -> tuple[
        MetadataTableMatch,
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

            like_query = f"%{query}%"

            rows = connection.execute(
                """
                SELECT DISTINCT
                    t.full_name,
                    t.layer,
                    COALESCE(
                        (
                            SELECT description
                            FROM metadata_table_description td2
                            WHERE td2.table_id = t.id
                            ORDER BY
                                td2.is_primary DESC,
                                td2.id ASC
                            LIMIT 1
                        ),
                        ''
                    ) AS description
                FROM metadata_table t
                LEFT JOIN metadata_table_description td
                    ON td.table_id = t.id
                WHERE
                    t.batch_id = ?
                    AND (
                        t.full_name LIKE ?
                        OR td.description LIKE ?
                    )
                ORDER BY t.full_name
                LIMIT ?
                """,
                (
                    batch_id,
                    like_query.lower(),
                    like_query,
                    limit,
                ),
            ).fetchall()

            return tuple(
                MetadataTableMatch(
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
        MetadataColumnMatch,
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

            like_query = f"%{query}%"

            rows = connection.execute(
                """
                SELECT DISTINCT
                    t.full_name
                        AS table_full_name,

                    COALESCE(
                        (
                            SELECT description
                            FROM metadata_table_description td
                            WHERE td.table_id = t.id
                            ORDER BY
                                td.is_primary DESC,
                                td.id ASC
                            LIMIT 1
                        ),
                        ''
                    ) AS table_description,

                    c.name,
                    c.data_type,

                    COALESCE(
                        (
                            SELECT description
                            FROM metadata_column_description cd2
                            WHERE cd2.column_id = c.id
                            ORDER BY
                                cd2.is_primary DESC,
                                cd2.id ASC
                            LIMIT 1
                        ),
                        ''
                    ) AS column_description

                FROM metadata_column c

                JOIN metadata_table t
                    ON t.id = c.table_id

                LEFT JOIN metadata_column_description cd
                    ON cd.column_id = c.id

                WHERE
                    t.batch_id = ?
                    AND (
                        c.name LIKE ?
                        OR cd.description LIKE ?
                    )

                ORDER BY
                    t.full_name,
                    c.name

                LIMIT ?
                """,
                (
                    batch_id,
                    like_query.lower(),
                    like_query,
                    limit,
                ),
            ).fetchall()

            return tuple(
                MetadataColumnMatch(
                    table_full_name=(
                        row[
                            "table_full_name"
                        ]
                    ),

                    table_description=(
                        row[
                            "table_description"
                        ]
                        or ""
                    ),

                    name=row["name"],

                    description=(
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
        MetadataColumnMatch,
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
                    t.full_name
                        AS table_full_name,

                    COALESCE(
                        (
                            SELECT description
                            FROM metadata_table_description td
                            WHERE td.table_id = t.id
                            ORDER BY
                                td.is_primary DESC,
                                td.id ASC
                            LIMIT 1
                        ),
                        ''
                    ) AS table_description,

                    c.name,
                    c.data_type,

                    COALESCE(
                        (
                            SELECT description
                            FROM metadata_column_description cd
                            WHERE cd.column_id = c.id
                            ORDER BY
                                cd.is_primary DESC,
                                cd.id ASC
                            LIMIT 1
                        ),
                        ''
                    ) AS column_description

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
                MetadataColumnMatch(
                    table_full_name=(
                        row[
                            "table_full_name"
                        ]
                    ),

                    table_description=(
                        row[
                            "table_description"
                        ]
                        or ""
                    ),

                    name=row["name"],

                    description=(
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