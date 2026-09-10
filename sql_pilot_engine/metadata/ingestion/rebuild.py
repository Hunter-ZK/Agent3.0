from __future__ import annotations

import gc
import os
import sqlite3

from dataclasses import dataclass
from pathlib import Path

from sql_pilot_engine.metadata.ingestion.excel import (
    ExcelMetadataImportResult,
    import_metadata_excel,
)

from sql_pilot_engine.metadata.schema import (
    METADATA_SCHEMA_VERSION,
    MetadataProvenance,
    initialize_metadata_database,
    rebuild_metadata_fts,
    write_build_info,
)

from sql_pilot_engine.standards.ingestion.excel import (
    StandardsImportResult,
    import_standards_excel,
)


@dataclass(
    frozen=True,
    slots=True,
)
class MetadataDatabaseRebuildResult:
    """
    一次完整 metadata.db rebuild 的结果。
    """

    database_path: Path

    schema_version: int

    provenance: MetadataProvenance

    metadata: (
        ExcelMetadataImportResult
    )

    standards: (
        StandardsImportResult
        | None
    )


def rebuild_metadata_database(
    *,
    metadata_source_path: (
        str | Path
    ),

    database_path: (
        str | Path
    ),

    metadata_source_name: (
        str | None
    ) = None,

    metadata_source_label: str = "",

    metadata_source_ref: (
        str | None
    ) = None,

    standards_source_path: (
        str | Path | None
    ) = None,

    standards_source_name: (
        str | None
    ) = None,

    standards_source_label: str = "",
) -> MetadataDatabaseRebuildResult:
    """
    全量、原子重建 metadata.db。

    External Sources
        ↓
    metadata.db.building
        ↓
    Physical Metadata Import
        ↓
    Standards Import
        ↓
    Build Validation
        ↓
    FTS Rebuild
        ↓
    Build Info
        ↓
    SQLite Integrity Check
        ↓
    os.replace()
        ↓
    metadata.db

    不执行 schema migration。

    Runtime 不调用本函数。
    """

    metadata_source = Path(
        metadata_source_path
    )

    target = Path(
        database_path
    )

    if not metadata_source.exists():
        raise FileNotFoundError(
            metadata_source
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    building = target.with_name(
        target.name + ".building"
    )

    if building.exists():
        building.unlink()

    standards_source = (
        None
        if standards_source_path
        is None
        else Path(
            standards_source_path
        )
    )

    if (
        standards_source
        is not None
        and not standards_source.exists()
    ):
        raise FileNotFoundError(
            standards_source
        )

    try:

        # ==================================================
        # 1. 创建全新的临时数据库
        # ==================================================

        initialize_metadata_database(
            building
        )

        # ==================================================
        # 2. Physical Metadata
        # ==================================================

        metadata_result = (
            import_metadata_excel(
                metadata_source,
                building,
            )
        )

        if (
            metadata_result
            .table_count
            <= 0
        ):
            raise RuntimeError(
                "Metadata rebuild aborted: "
                "no metadata tables imported."
            )

        # ==================================================
        # 3. Standards
        # ==================================================

        standards_result = None

        if (
            standards_source
            is not None
        ):
            standards_result = (
                import_standards_excel(
                    standards_source,
                    building,
                )
            )

        # ==================================================
        # 4. Build Validation + FTS + Build Info
        # ==================================================

        connection = sqlite3.connect(
            building
        )

        try:

            connection.execute(
                "PRAGMA foreign_keys = ON"
            )

            _validate_metadata_build(
                connection,
                provenance=(
                    metadata_result
                    .provenance
                ),
            )

            rebuild_metadata_fts(
                connection
            )

            write_build_info(
                connection,

                metadata_source_name=(
                    metadata_source_name
                    or metadata_source.name
                ),

                metadata_source_label=(
                    metadata_source_label
                ),

                provenance=(
                    metadata_result
                    .provenance
                ),

                source_ref=(
                    metadata_source_ref
                    or metadata_source.name
                ),

                standards_source_name=(
                    (
                        standards_source_name
                        or standards_source.name
                    )
                    if standards_source
                    is not None
                    else ""
                ),

                standards_source_label=(
                    standards_source_label
                ),
            )

            _validate_sqlite_integrity(
                connection
            )

            connection.commit()

        finally:
            connection.close()

        # Windows 下确保 SQLite / openpyxl
        # 等临时对象不再持有 building 文件句柄。
        gc.collect()

        # ==================================================
        # 5. Atomic Replace
        # ==================================================

        os.replace(
            building,
            target,
        )

        return (
            MetadataDatabaseRebuildResult(
                database_path=target,

                schema_version=(
                    METADATA_SCHEMA_VERSION
                ),

                provenance=(
                    metadata_result
                    .provenance
                ),

                metadata=(
                    metadata_result
                ),

                standards=(
                    standards_result
                ),
            )
        )

    except Exception:

        gc.collect()

        if building.exists():
            building.unlink()

        raise


def _validate_metadata_build(
    connection: sqlite3.Connection,
    *,
    provenance: MetadataProvenance,
) -> None:
    """
    Metadata Build Gate。

    所有 provenance：
        检查结构一致性。

    AUTHORITATIVE：
        再检查正式 Metadata
        最低完整性要求。

    注意：
        这里不是 Runtime Coverage。
    """

    table_count = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM metadata_table
            """
        ).fetchone()[0]
    )

    column_count = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM metadata_column
            """
        ).fetchone()[0]
    )

    if table_count <= 0:
        raise RuntimeError(
            "Metadata build contains "
            "no tables."
        )

    if column_count <= 0:
        raise RuntimeError(
            "Metadata build contains "
            "no columns."
        )

    # --------------------------------------------------
    # Table column_count
    # vs
    # actual metadata_column count
    # --------------------------------------------------

    column_count_mismatches = (
        connection.execute(
            """
            SELECT
                t.full_name,
                t.column_count,
                COUNT(c.id)
                    AS actual_count

            FROM metadata_table t

            LEFT JOIN metadata_column c
                ON c.table_id = t.id

            GROUP BY
                t.id,
                t.full_name,
                t.column_count

            HAVING
                t.column_count
                <> COUNT(c.id)
            """
        )
        .fetchall()
    )

    if column_count_mismatches:
        raise RuntimeError(
            "Metadata build contains "
            "table/column_count mismatch: "
            f"{column_count_mismatches!r}"
        )

    # --------------------------------------------------
    # AUTHORITATIVE-only Gate
    # --------------------------------------------------

    if (
        provenance
        is not MetadataProvenance
        .AUTHORITATIVE
    ):
        return

    unqualified_tables = (
        connection.execute(
            """
            SELECT full_name
            FROM metadata_table
            WHERE
                project = ''
                OR instr(
                    full_name,
                    '.'
                ) = 0
            """
        )
        .fetchall()
    )

    if unqualified_tables:
        raise RuntimeError(
            "AUTHORITATIVE metadata "
            "contains unqualified tables: "
            f"{unqualified_tables[:10]!r}"
        )

    missing_data_types = (
        connection.execute(
            """
            SELECT
                t.full_name,
                c.name

            FROM metadata_column c

            JOIN metadata_table t
                ON t.id = c.table_id

            WHERE
                trim(c.data_type) = ''

            LIMIT 20
            """
        )
        .fetchall()
    )

    if missing_data_types:
        raise RuntimeError(
            "AUTHORITATIVE metadata "
            "contains columns without "
            "data_type: "
            f"{missing_data_types!r}"
        )


def _validate_sqlite_integrity(
    connection: sqlite3.Connection,
) -> None:
    """
    SQLite 自身的基础完整性检查。
    """

    foreign_key_errors = (
        connection.execute(
            "PRAGMA foreign_key_check"
        )
        .fetchall()
    )

    if foreign_key_errors:
        raise RuntimeError(
            "Metadata rebuild aborted: "
            "foreign key errors="
            f"{foreign_key_errors!r}"
        )

    integrity_result = (
        connection.execute(
            "PRAGMA integrity_check"
        )
        .fetchone()
    )

    if (
        integrity_result is None
        or integrity_result[0] != "ok"
    ):
        raise RuntimeError(
            "Metadata rebuild aborted: "
            "SQLite integrity_check failed."
        )


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Rebuild Agent3 metadata "
            "SQLite database."
        )
    )

    parser.add_argument(
        "--metadata-source",
        required=True,
        help=(
            "Path to metadata Excel "
            "source file."
        ),
    )

    parser.add_argument(
        "--target-db",
        required=True,
        help=(
            "Path to target SQLite "
            "database."
        ),
    )

    parser.add_argument(
        "--standards-source",
        default=None,
        help=(
            "Path to standards Excel "
            "source file."
        ),
    )

    parser.add_argument(
        "--metadata-label",
        default="",
        help=(
            "Metadata source label."
        ),
    )

    parser.add_argument(
        "--standards-label",
        default="",
        help=(
            "Standards source label."
        ),
    )

    args = parser.parse_args()

    result = (
        rebuild_metadata_database(
            metadata_source_path=(
                args.metadata_source
            ),

            database_path=(
                args.target_db
            ),

            standards_source_path=(
                args.standards_source
            ),

            metadata_source_label=(
                args.metadata_label
            ),

            standards_source_label=(
                args.standards_label
            ),
        )
    )

    print(
        "Metadata rebuild completed."
    )

    print(
        f"Database: "
        f"{result.database_path}"
    )

    print(
        f"Schema version: "
        f"{result.schema_version}"
    )

    print(
        f"Provenance: "
        f"{result.provenance.value}"
    )

    print(
        f"Tables: "
        f"{result.metadata.table_count}"
    )

    print(
        f"Columns: "
        f"{result.metadata.column_count}"
    )