from __future__ import annotations

from pathlib import Path

from sql_pilot_engine.app.sql_review_factory import (
    build_sql_review_service,
)
from sql_pilot_engine.evaluation.sql_review_cases import (
    SQL_REVIEW_GOLDEN_CASES,
)
from sql_pilot_engine.evaluation.sql_review_runner import (
    SQLReviewEvaluationRunner,
)
from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)


def main() -> None:

    metadata_db = Path(
        "data/metadata/"
        "agent_metadata.db"
    )

    if not metadata_db.is_file():
        raise FileNotFoundError(
            f"Metadata DB not found: "
            f"{metadata_db.resolve()}"
        )

    def metadata_provider_factory():
        return (
            SQLiteMetadataRepository(
                metadata_db
            )
        )

    service = (
        build_sql_review_service(
            metadata_provider_factory=(
                metadata_provider_factory
            )
        )
    )

    runner = (
        SQLReviewEvaluationRunner(
            service=service
        )
    )

    summary = runner.run(
        SQL_REVIEW_GOLDEN_CASES
    )

    print(
        "=" * 72
    )
    print(
        "Agent3.0 · "
        "SQL Review Evaluation V0.1"
    )
    print(
        "=" * 72
    )

    print()
    print(
        "total:",
        summary.total,
    )
    print(
        "passed:",
        summary.passed,
    )
    print(
        "failed:",
        summary.failed,
    )
    print(
        "pass_rate:",
        f"{summary.pass_rate:.1%}",
    )

    print()

    for case in summary.cases:

        status = (
            "PASS"
            if case.passed
            else "FAIL"
        )

        print(
            f"[{status}] "
            f"{case.case_id}"
        )

        print(
            "  status:",
            case.actual_status,
        )

        print(
            "  success:",
            case.actual_success,
        )

        print(
            "  trusted_sql:",
            case.trusted_sql_present,
        )

        if case.issue_rule_ids:
            print(
                "  rules:",
                ", ".join(
                    case.issue_rule_ids
                ),
            )

        for failure in (
            case.failures
        ):
            print(
                "  -",
                failure,
            )

        print()


if __name__ == "__main__":
    main()