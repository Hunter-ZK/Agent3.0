from __future__ import annotations

import argparse

from pathlib import Path

from sql_pilot_engine.metadata.ingestion.excel import (
    load_metadata_excel,
)

from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Import warehouse metadata "
            "from Excel into SQLite."
        )
    )

    parser.add_argument(
        "source",
        type=Path,
    )

    parser.add_argument(
        "database",
        type=Path,
    )

    parser.add_argument(
        "--snapshot-label",
        required=True,
    )

    args = parser.parse_args()

    result = load_metadata_excel(
        args.source,

        snapshot_label=(
            args.snapshot_label
        ),
    )

    repository = (
        SQLiteMetadataRepository(
            args.database
        )
    )

    repository.initialize()

    batch_id = (
        repository.import_snapshot(
            result.snapshot,
            activate=True,
        )
    )

    print(
        "Metadata import completed."
    )

    print(
        f"Batch ID: {batch_id}"
    )

    print(
        "Tables:",
        len(
            result.snapshot.tables
        ),
    )

    print(
        "Columns:",
        sum(
            len(table.columns)
            for table
            in result.snapshot.tables
        ),
    )

    print(
        "Raw rows:",
        result.raw_rows,
    )

    print(
        "Accepted rows:",
        result.accepted_rows,
    )

    print(
        "Duplicate rows:",
        result.duplicate_rows,
    )

    print(
        "Skipped rows:",
        result.skipped_rows,
    )

    print(
        "Database:",
        args.database,
    )


if __name__ == "__main__":
    main()