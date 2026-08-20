from __future__ import annotations

import sqlite3

from pathlib import Path


METADATA_SCHEMA_VERSION = 2


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata_build_info (
    id INTEGER PRIMARY KEY
        CHECK (id = 1),

    schema_version INTEGER NOT NULL,

    built_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    metadata_source_name TEXT NOT NULL
        DEFAULT '',

    metadata_source_label TEXT NOT NULL
        DEFAULT '',

    standards_source_name TEXT NOT NULL
        DEFAULT '',

    standards_source_label TEXT NOT NULL
        DEFAULT ''
);


CREATE TABLE IF NOT EXISTS metadata_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    full_name TEXT NOT NULL UNIQUE,

    description TEXT NOT NULL
        DEFAULT '',

    layer TEXT NOT NULL
        DEFAULT '',

    row_count INTEGER,

    size_bytes INTEGER
);


CREATE TABLE IF NOT EXISTS metadata_column (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    table_id INTEGER NOT NULL,

    name TEXT NOT NULL,

    description TEXT NOT NULL
        DEFAULT '',

    data_type TEXT NOT NULL
        DEFAULT '',

    nullable INTEGER,

    ordinal_position INTEGER,

    is_partition INTEGER,

    distinct_count INTEGER,

    FOREIGN KEY (table_id)
        REFERENCES metadata_table(id)
        ON DELETE CASCADE,

    UNIQUE (
        table_id,
        name
    )
);


CREATE INDEX IF NOT EXISTS
idx_metadata_table_name
ON metadata_table(full_name);


CREATE INDEX IF NOT EXISTS
idx_metadata_column_name
ON metadata_column(name);


CREATE TABLE IF NOT EXISTS standard_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    rule_code TEXT NOT NULL UNIQUE,

    rule_type TEXT NOT NULL,

    category TEXT NOT NULL
        DEFAULT '',

    rule_text TEXT NOT NULL,

    status TEXT NOT NULL,

    evidence TEXT NOT NULL
        DEFAULT '',

    example TEXT NOT NULL
        DEFAULT '',

    note TEXT NOT NULL
        DEFAULT '',

    source_sheet TEXT NOT NULL
        DEFAULT ''
);


CREATE INDEX IF NOT EXISTS
idx_standard_rule_category
ON standard_rule(category);


CREATE TABLE IF NOT EXISTS canonical_root (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    canonical_concept TEXT NOT NULL,

    chinese_expression TEXT NOT NULL UNIQUE,

    canonical_root TEXT NOT NULL,

    root_type TEXT NOT NULL
        DEFAULT '',

    status TEXT NOT NULL,

    source TEXT NOT NULL
        DEFAULT '',

    note TEXT NOT NULL
        DEFAULT ''
);


CREATE INDEX IF NOT EXISTS
idx_canonical_root_concept
ON canonical_root(canonical_concept);


CREATE INDEX IF NOT EXISTS
idx_canonical_root_value
ON canonical_root(canonical_root);


CREATE VIRTUAL TABLE IF NOT EXISTS
metadata_table_fts
USING fts5(
    full_name,
    description,
    tokenize='trigram'
);


CREATE VIRTUAL TABLE IF NOT EXISTS
metadata_column_fts
USING fts5(
    name,
    description,
    tokenize='trigram'
);
"""


def initialize_metadata_database(
    database_path: str | Path,
) -> None:
    """
    仅供 Maintenance / Rebuild 使用。

    Agent Runtime 禁止调用。
    """

    path = Path(database_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(
        path
    ) as connection:

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        connection.executescript(
            SCHEMA_SQL
        )


def rebuild_metadata_fts(
    connection: sqlite3.Connection,
) -> None:
    """
    在一次完整 Metadata Build 结束后，
    根据事实表重新构建独立 FTS 索引。

    不使用：
    - external content
    - trigger

    因为 metadata.db 本身采用全量重建。
    """

    connection.execute(
        "DELETE FROM metadata_table_fts"
    )

    connection.execute(
        """
        INSERT INTO metadata_table_fts (
            rowid,
            full_name,
            description
        )
        SELECT
            id,
            full_name,
            description
        FROM metadata_table
        """
    )

    connection.execute(
        "DELETE FROM metadata_column_fts"
    )

    connection.execute(
        """
        INSERT INTO metadata_column_fts (
            rowid,
            name,
            description
        )
        SELECT
            id,
            name,
            description
        FROM metadata_column
        """
    )


def write_build_info(
    connection: sqlite3.Connection,
    *,
    metadata_source_name: str,
    metadata_source_label: str = "",
    standards_source_name: str = "",
    standards_source_label: str = "",
) -> None:

    connection.execute(
        """
        INSERT INTO metadata_build_info (
            id,
            schema_version,
            metadata_source_name,
            metadata_source_label,
            standards_source_name,
            standards_source_label
        )
        VALUES (
            1,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        ON CONFLICT(id)
        DO UPDATE SET
            schema_version = excluded.schema_version,
            built_at = CURRENT_TIMESTAMP,
            metadata_source_name =
                excluded.metadata_source_name,
            metadata_source_label =
                excluded.metadata_source_label,
            standards_source_name =
                excluded.standards_source_name,
            standards_source_label =
                excluded.standards_source_label
        """,
        (
            METADATA_SCHEMA_VERSION,
            metadata_source_name,
            metadata_source_label,
            standards_source_name,
            standards_source_label,
        ),
    )