from __future__ import annotations

import argparse
from pathlib import Path

from sql_pilot_engine.app.sql_review_factory import (
    build_sql_review_capability,
)
from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)
from sql_pilot_engine.schemas.sql_review import (
    SQLReviewInput,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Agent3.0 SQL Review V0.1 Demo"
        )
    )

    parser.add_argument(
        "--sql",
        type=str,
        default=None,
        help="SQL text to review.",
    )

    parser.add_argument(
        "--sql-file",
        type=str,
        default=None,
        help="Read SQL from file.",
    )

    parser.add_argument(
        "--metadata-db",
        type=str,
        default=(
            "data/metadata/"
            "agent_metadata.db"
        ),
    )

    return parser.parse_args()


def load_sql(
    args: argparse.Namespace,
) -> str:
    if args.sql:
        return args.sql

    if args.sql_file:
        return Path(
            args.sql_file
        ).read_text(
            encoding="utf-8"
        )

    raise ValueError(
        "Either --sql or --sql-file "
        "must be provided."
    )


def main() -> None:
    args = parse_args()

    sql = load_sql(
        args
    )

    metadata_db = Path(
        args.metadata_db
    )

    if not metadata_db.is_file():
        raise FileNotFoundError(
            "Metadata database not found: "
            f"{metadata_db.resolve()}"
        )

    def build_metadata_provider():
        return (
            SQLiteMetadataRepository(
                metadata_db
            )
        )

    service = (
        build_sql_review_capability(
            metadata_provider_factory=(
                build_metadata_provider
            )
        )
    )

    result = service.review(
        SQLReviewInput(
            sql=sql,
        )
    )

    print(
        "=" * 72
    )
    print(
        "Agent3.0 · SQL Review V0.1"
    )
    print(
        "=" * 72
    )

    print()
    print("[1] Original SQL")
    print(result.original_sql)

    print()
    print("[2] Review Status")

    print(
        "trace_id:",
        result.trace_id,
    )

    print(
        "success:",
        result.success,
    )
    print(
        "status:",
        result.review_status,
    )
    print(
        "risk:",
        result.risk_level,
    )
    print(
        "fix_applied:",
        result.fix_applied,
    )

    print()
    print("[3] Issues")

    if not result.issues:
        print("None")
    else:
        for index, issue in enumerate(
            result.issues,
            start=1,
        ):
            print(
                f"{index}. "
                f"[{issue.severity}] "
                f"{issue.rule_id}"
            )
            print(
                "   ",
                issue.message,
            )

            if issue.suggestion:
                print(
                    "   suggestion:",
                    issue.suggestion,
                )

            print(
                "   blocking:",
                issue.blocking,
            )
            print(
                "   auto_fixable:",
                issue.auto_fixable,
            )

    print()
    print("[4] Route History")
    print(
        " -> ".join(
            result.route_history
        )
        or "None"
    )

    print()
    print("[5] Trusted SQL")

    if result.trusted_sql:
        print(
            result.trusted_sql
        )
    else:
        print(
            "No Trusted SQL."
        )

    if result.error_message:
        print()
        print("[6] Error")
        print(
            result.error_message
        )


if __name__ == "__main__":
    main()