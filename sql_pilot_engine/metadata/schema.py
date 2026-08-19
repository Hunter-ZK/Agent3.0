from __future__ import annotations

import sqlite3

from pathlib import Path


SCHEMA_SQL = """
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

    description TEXT NOT NULL
        DEFAULT '',

    layer TEXT NOT NULL
        DEFAULT '',

    FOREIGN KEY (batch_id)
        REFERENCES metadata_batch(id)
        ON DELETE CASCADE,

    UNIQUE (
        batch_id,
        full_name
    )
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
"""


def initialize_metadata_database(
    database_path: str | Path,
) -> None:

    path = Path(database_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(path) as connection:

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        connection.executescript(
            SCHEMA_SQL
        )