from __future__ import annotations

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
    database_path: Path

    schema_version: int

    metadata: ExcelMetadataImportResult

    standards: (
        StandardsImportResult
        | None
    )


def rebuild_metadata_database(
    *,
    metadata_source_path: (
        str | Path
    ),
    database_path: str | Path,

    metadata_source_name: (
        str | None
    ) = None,

    metadata_source_label: str = "",

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

    正确生命周期：

    External Sources
        ↓
    metadata.db.building
        ↓
    import
        ↓
    FTS rebuild
        ↓
    integrity validation
        ↓
    os.replace()
        ↓
    metadata.db

    不执行 schema migration。
    """

    metadata_source = Path(
        metadata_source_path
    )

    target = Path(
        database_path
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

    try:
        # --------------------------------------------------
        # 1. 创建全新的临时事实库
        # --------------------------------------------------

        initialize_metadata_database(
            building
        )

        # --------------------------------------------------
        # 2. 导入 Physical Metadata
        # --------------------------------------------------

        metadata_result = (
            import_metadata_excel(
                metadata_source,
                building,
            )
        )

        if (
            metadata_result.table_count
            <= 0
        ):
            raise RuntimeError(
                "Metadata rebuild aborted: "
                "no metadata tables imported."
            )

        # --------------------------------------------------
        # 3. 导入 Standards
        # --------------------------------------------------

        standards_result = None

        if standards_source is not None:

            standards_result = (
                import_standards_excel(
                    standards_source,
                    building,
                )
            )

        # --------------------------------------------------
        # 4. FTS + Build Provenance
        # --------------------------------------------------

        connection = sqlite3.connect(
            building
        )

        try:
            connection.execute(
                "PRAGMA foreign_keys = ON"
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

            fk_errors = (
                connection.execute(
                    "PRAGMA foreign_key_check"
                )
                .fetchall()
            )

            if fk_errors:
                raise RuntimeError(
                    "Metadata rebuild aborted: "
                    f"foreign key errors="
                    f"{fk_errors!r}"
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

            connection.commit()

        finally:
            # Windows 下必须确保真正释放文件句柄。
            connection.close()


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

                metadata=(
                    metadata_result
                ),

                standards=(
                    standards_result
                ),
            )
        )

    except Exception:

        if building.exists():
            building.unlink()

        raise