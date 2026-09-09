from __future__ import annotations

import sqlite3

from enum import Enum
from pathlib import Path


METADATA_SCHEMA_VERSION = 3


class MetadataProvenance(str, Enum):
    """
    Metadata build provenance。

    AUTHORITATIVE:
        正式权威盘点数据。

    SYNTHETIC:
        测试 / Demo 构造数据。

    PARTIAL:
        旧格式或尚未完成盘点的数据。

    Provenance 只影响 Stage Gate，
    不改变 Runtime Lookup Semantic。
    """

    AUTHORITATIVE = "AUTHORITATIVE"
    SYNTHETIC = "SYNTHETIC"
    PARTIAL = "PARTIAL"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata_build_info (
    id INTEGER PRIMARY KEY
        CHECK (id = 1),

    schema_version INTEGER NOT NULL,

    built_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    provenance TEXT NOT NULL
        DEFAULT 'PARTIAL'
        CHECK (
            provenance IN (
                'AUTHORITATIVE',
                'SYNTHETIC',
                'PARTIAL'
            )
        ),

    source_ref TEXT NOT NULL
        DEFAULT '',

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

    project TEXT NOT NULL
        DEFAULT '',

    table_name TEXT NOT NULL,

    code_path TEXT,

    partition_fields_json TEXT NOT NULL
        DEFAULT '[]',

    column_count INTEGER NOT NULL
        DEFAULT 0
        CHECK (column_count >= 0),

    source_system TEXT,

    processing_node TEXT,

    description TEXT NOT NULL
        DEFAULT '',

    statistical_regime TEXT,

    business_name TEXT,

    related_business_json TEXT NOT NULL
        DEFAULT '[]',

    asset_category TEXT,

    report_name TEXT,

    purpose TEXT,

    grain TEXT,

    business_key_json TEXT NOT NULL
        DEFAULT '[]',

    owning_department TEXT,

    data_origin TEXT,

    data_cycle TEXT,

    schedule_cycle TEXT,

    update_mode TEXT,

    data_period_field TEXT,

    first_period TEXT,

    latest_period TEXT,

    period_note TEXT,

    last_updated_at TEXT,

    row_count INTEGER,

    size_bytes INTEGER,

    maintainer TEXT,

    asset_status TEXT,

    last_verified_at TEXT,

    remark TEXT,

    UNIQUE (
        project,
        table_name
    ),

    CHECK (
        (
            project = ''
            AND full_name = table_name
        )
        OR
        (
            project <> ''
            AND full_name =
                project || '.' || table_name
        )
    )
);


CREATE INDEX IF NOT EXISTS
idx_metadata_table_full_name
ON metadata_table(full_name);


CREATE INDEX IF NOT EXISTS
idx_metadata_table_table_name
ON metadata_table(table_name);


CREATE INDEX IF NOT EXISTS
idx_metadata_table_project
ON metadata_table(project);


CREATE TABLE IF NOT EXISTS metadata_table_upstream (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    table_id INTEGER NOT NULL,

    upstream_full_name TEXT NOT NULL,

    ordinal_position INTEGER NOT NULL,

    FOREIGN KEY (table_id)
        REFERENCES metadata_table(id)
        ON DELETE CASCADE,

    UNIQUE (
        table_id,
        upstream_full_name
    ),

    UNIQUE (
        table_id,
        ordinal_position
    )
);


CREATE INDEX IF NOT EXISTS
idx_metadata_table_upstream_name
ON metadata_table_upstream(
    upstream_full_name
);


CREATE TABLE IF NOT EXISTS metadata_column (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    table_id INTEGER NOT NULL,

    name TEXT NOT NULL,

    ordinal_position INTEGER NOT NULL
        CHECK (ordinal_position > 0),

    data_type TEXT NOT NULL
        DEFAULT '',

    nullable INTEGER
        CHECK (
            nullable IS NULL
            OR nullable IN (0, 1)
        ),

    is_partition INTEGER NOT NULL
        DEFAULT 0
        CHECK (
            is_partition IN (0, 1)
        ),

    processing_kind TEXT,

    description TEXT NOT NULL
        DEFAULT '',

    definition TEXT,

    collection_rule TEXT,

    validation_rule TEXT,

    processing_logic TEXT,

    data_format TEXT,

    unit TEXT,

    is_code_field INTEGER NOT NULL
        DEFAULT 0
        CHECK (
            is_code_field IN (0, 1)
        ),

    code_table_id TEXT,

    is_dimension INTEGER NOT NULL
        DEFAULT 0
        CHECK (
            is_dimension IN (0, 1)
        ),

    dimension_table TEXT,

    dimension_column TEXT,

    is_metric INTEGER NOT NULL
        DEFAULT 0
        CHECK (
            is_metric IN (0, 1)
        ),

    metric_formula TEXT,

    metric_aggregation TEXT,

    lineage_source TEXT,

    lineage_confirmation_status TEXT,

    remark TEXT,

    FOREIGN KEY (table_id)
        REFERENCES metadata_table(id)
        ON DELETE CASCADE,

    UNIQUE (
        table_id,
        name
    ),

    UNIQUE (
        table_id,
        ordinal_position
    )
);


CREATE INDEX IF NOT EXISTS
idx_metadata_column_name
ON metadata_column(name);


CREATE INDEX IF NOT EXISTS
idx_metadata_column_table_id
ON metadata_column(table_id);


CREATE TABLE IF NOT EXISTS metadata_column_upstream (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    column_id INTEGER NOT NULL,

    upstream_table_full_name TEXT NOT NULL,

    upstream_column_name TEXT NOT NULL,

    ordinal_position INTEGER NOT NULL,

    FOREIGN KEY (column_id)
        REFERENCES metadata_column(id)
        ON DELETE CASCADE,

    UNIQUE (
        column_id,
        upstream_table_full_name,
        upstream_column_name
    ),

    UNIQUE (
        column_id,
        ordinal_position
    )
);


CREATE INDEX IF NOT EXISTS
idx_metadata_column_upstream_identity
ON metadata_column_upstream(
    upstream_table_full_name,
    upstream_column_name
);


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
    table_name,
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
    创建一份全新的 Metadata SQLite Schema。

    仅供：

    - Maintenance
    - Rebuild
    - Tests

    使用。

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
    根据 Metadata 事实表全量重建 FTS 索引。

    metadata.db 本身采用全量重建，
    因此不使用 external-content FTS
    或同步 trigger。
    """

    connection.execute(
        "DELETE FROM metadata_table_fts"
    )

    connection.execute(
        """
        INSERT INTO metadata_table_fts (
            rowid,
            full_name,
            table_name,
            description
        )
        SELECT
            id,
            full_name,
            table_name,
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
    provenance: (
        MetadataProvenance
        | str
    ) = MetadataProvenance.PARTIAL,
    source_ref: str = "",
) -> None:
    """
    写入当前 metadata.db 的构建信息。

    注意：

    provenance 是整批 Metadata 的
    build-level provenance。

    它不是 Runtime 的 Metadata Coverage。
    """

    if isinstance(
        provenance,
        MetadataProvenance,
    ):
        provenance_value = (
            provenance.value
        )
    else:
        provenance_value = (
            MetadataProvenance(
                provenance
                .strip()
                .upper()
            )
            .value
        )

    connection.execute(
        """
        INSERT INTO metadata_build_info (
            id,
            schema_version,
            provenance,
            source_ref,
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
            ?,
            ?,
            ?
        )
        ON CONFLICT(id)
        DO UPDATE SET
            schema_version =
                excluded.schema_version,

            built_at =
                CURRENT_TIMESTAMP,

            provenance =
                excluded.provenance,

            source_ref =
                excluded.source_ref,

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
            provenance_value,
            source_ref.strip(),
            metadata_source_name.strip(),
            metadata_source_label.strip(),
            standards_source_name.strip(),
            standards_source_label.strip(),
        ),
    )