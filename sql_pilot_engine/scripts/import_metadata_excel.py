from __future__ import annotations

import argparse

from pathlib import Path

from sql_pilot_engine.metadata.ingestion.rebuild import (
    rebuild_metadata_database,
)


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Rebuild Agent3 metadata.db "
            "from metadata Excel."
        )
    )

    parser.add_argument(
        "source",
        type=Path,
        help=(
            "Metadata Excel source file."
        ),
    )

    parser.add_argument(
        "database",
        type=Path,
        help=(
            "Target metadata SQLite "
            "database."
        ),
    )

    parser.add_argument(
        "--snapshot-label",
        default="",
        help=(
            "Metadata source version "
            "label, for example "
            "2026-09."
        ),
    )

    parser.add_argument(
        "--standards-source",
        type=Path,
        default=None,
        help=(
            "Optional standards Excel "
            "source."
        ),
    )

    parser.add_argument(
        "--standards-label",
        default="",
        help=(
            "Optional standards "
            "version label."
        ),
    )

    args = parser.parse_args()

    result = (
        rebuild_metadata_database(
            metadata_source_path=(
                args.source
            ),

            database_path=(
                args.database
            ),

            metadata_source_label=(
                args.snapshot_label
            ),

            standards_source_path=(
                args.standards_source
            ),

            standards_source_label=(
                args.standards_label
            ),
        )
    )

    print()
    print(
        "Metadata rebuild completed."
    )

    print(
        "=" * 60
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
        f"Source format: "
        f"{result.metadata.source_format}"
    )

    print(
        f"Tables: "
        f"{result.metadata.table_count}"
    )

    print(
        f"Columns: "
        f"{result.metadata.column_count}"
    )

    print(
        f"Raw rows: "
        f"{result.metadata.raw_rows}"
    )

    print(
        f"Accepted rows: "
        f"{result.metadata.accepted_rows}"
    )

    print(
        f"Duplicate rows: "
        f"{result.metadata.duplicate_rows}"
    )

    print(
        f"Skipped rows: "
        f"{result.metadata.skipped_rows}"
    )

    print(
        "=" * 60
    )

    print(
        f"Database: "
        f"{result.database_path}"
    )


if __name__ == "__main__":
    main()