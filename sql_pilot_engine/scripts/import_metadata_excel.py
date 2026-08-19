from __future__ import annotations

import argparse

from pathlib import Path

from sql_pilot_engine.metadata.ingestion.excel import (
    import_metadata_excel,
)


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Import metadata Excel "
            "into persistent SQLite DB."
        )
    )

    parser.add_argument(
        "source",
        type=Path,

        help=(
            "Metadata Excel file."
        ),
    )

    parser.add_argument(
        "database",
        type=Path,

        help=(
            "Persistent SQLite "
            "metadata database."
        ),
    )

    parser.add_argument(
        "--snapshot-label",
        required=True,

        help=(
            "Metadata version label, "
            "for example 2026-05."
        ),
    )

    args = parser.parse_args()

    result = import_metadata_excel(
        args.source,

        args.database,

        snapshot_label=(
            args.snapshot_label
        ),
    )

    print()
    print(
        "Metadata import completed."
    )
    print(
        "=" * 50
    )

    print(
        f"Batch ID:       "
        f"{result.batch_id}"
    )

    print(
        f"Tables:         "
        f"{result.table_count}"
    )

    print(
        f"Columns:        "
        f"{result.column_count}"
    )

    print(
        f"Raw rows:       "
        f"{result.raw_rows}"
    )

    print(
        f"Accepted rows:  "
        f"{result.accepted_rows}"
    )

    print(
        f"Duplicate rows: "
        f"{result.duplicate_rows}"
    )

    print(
        f"Skipped rows:   "
        f"{result.skipped_rows}"
    )

    print(
        "=" * 50
    )

    print(
        f"Database: "
        f"{args.database}"
    )


if __name__ == "__main__":
    main()