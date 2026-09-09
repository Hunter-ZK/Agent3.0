from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path
from typing import Any


from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
    TableMetadata,
)
from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)
from sql_pilot_engine.program.enums import (
    ProgramAnalysisStatus,
    SourceBindingKind,
)
from sql_pilot_engine.program.models import (
    SQLProgram,
)
from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)
from sql_pilot_engine.simulation import (
    MaxComputeLocalSimulator,
    MaxComputeSimulationError,
)


# ============================================================
# CLI
# ============================================================


def _parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Execute a private production "
            "MaxCompute SQL Program inside "
            "Agent3.0 Local Simulator."
        )
    )

    parser.add_argument(
        "--sql",
        required=True,
        type=Path,
        help=(
            "Path to private production SQL."
        ),
    )

    parser.add_argument(
        "--metadata-db",
        required=True,
        type=Path,
        help=(
            "Path to authoritative "
            "Agent3.0 Metadata SQLite DB."
        ),
    )

    parser.add_argument(
        "--fixtures",
        required=True,
        type=Path,
        help=(
            "JSON fixture file. "
            "Every physical READ source "
            "must appear explicitly."
        ),
    )

    parser.add_argument(
        "--parameters",
        required=True,
        type=Path,
        help=(
            "JSON mapping of DataWorks "
            "parameter name to value."
        ),
    )

    parser.add_argument(
        "--preview-rows",
        type=int,
        default=20,
        help=(
            "Maximum number of rows to "
            "print for each write target."
        ),
    )

    return parser.parse_args()


# ============================================================
# JSON
# ============================================================


def _read_json(
    path: Path,
) -> Any:

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


# ============================================================
# Program Physical Tables
# ============================================================


def _collect_read_tables(
    program: SQLProgram,
) -> tuple[
    str,
    ...,
]:

    tables: list[
        str
    ] = []

    seen: set[
        str
    ] = set()

    for scope in (
        program.scope_analyses
    ):

        for binding in (
            scope.source_bindings
        ):

            if (
                binding.kind
                is not (
                    SourceBindingKind
                    .PHYSICAL_TABLE
                )
            ):
                continue

            table_name = (
                binding.physical_table
            )

            if table_name is None:
                raise RuntimeError(
                    (
                        "Physical SourceBinding "
                        "has no physical_table."
                    )
                )

            normalized = (
                table_name
                .strip()
                .lower()
            )

            if normalized in seen:
                continue

            seen.add(
                normalized
            )

            tables.append(
                normalized
            )

    return tuple(
        tables
    )


def _collect_write_tables(
    program: SQLProgram,
) -> tuple[
    str,
    ...,
]:

    tables: list[
        str
    ] = []

    seen: set[
        str
    ] = set()

    for statement in (
        program.statements
    ):

        target = (
            statement.write_target
        )

        if target is None:
            continue

        normalized = (
            target.table_name
            .strip()
            .lower()
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        tables.append(
            normalized
        )

    return tuple(
        tables
    )


# ============================================================
# Authoritative Metadata Resolution
# ============================================================


def _resolve_metadata(
    repository: SQLiteMetadataRepository,
    requested_table: str,
) -> TableMetadata:
    """
    使用与正式 4.3 相同的规则：

        qualified table
            → exact lookup

        bare table
            → 0 candidate = error
            → 1 candidate = canonical
            → >1 candidate = ambiguous

    这里是 example runner，
    不改变核心 Metadata Contract。
    """

    normalized = (
        requested_table
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # Canonical full name
    # --------------------------------------------------------

    if "." in normalized:

        result = (
            repository.get_table(
                normalized
            )
        )

        if (
            result.status
            is MetadataLookupStatus.ERROR
        ):
            raise RuntimeError(
                (
                    "Metadata error for "
                    f"{normalized}: "
                    f"{result.error_message}"
                )
            )

        if (
            result.status
            is MetadataLookupStatus.NOT_FOUND
        ):
            raise RuntimeError(
                (
                    "Metadata table not found: "
                    f"{normalized}"
                )
            )

        if result.table is None:
            raise RuntimeError(
                (
                    "MetadataProvider returned "
                    "FOUND without table for "
                    f"{normalized}"
                )
            )

        return result.table

    # --------------------------------------------------------
    # Bare table
    # --------------------------------------------------------

    candidates = (
        repository
        .find_table_identifiers(
            normalized
        )
    )

    if not candidates:

        raise RuntimeError(
            (
                "Metadata table not found: "
                f"{normalized}"
            )
        )

    if len(candidates) > 1:

        candidate_names = (
            ", ".join(
                candidate.full_name
                for candidate
                in candidates
            )
        )

        raise RuntimeError(
            (
                "Ambiguous Metadata table "
                f"{normalized!r}: "
                f"{candidate_names}"
            )
        )

    canonical = (
        candidates[0]
        .full_name
    )

    result = (
        repository.get_table(
            canonical
        )
    )

    if (
        result.status
        is not MetadataLookupStatus.FOUND
        or result.table is None
    ):
        raise RuntimeError(
            (
                "Metadata Catalog resolved "
                f"{normalized!r} to "
                f"{canonical!r}, but "
                "Provider could not load it."
            )
        )

    return result.table


# ============================================================
# Fixture Resolution
# ============================================================


def _find_fixture_rows(
    *,
    fixtures: dict[
        str,
        list[
            dict[
                str,
                Any,
            ]
        ],
    ],
    metadata: TableMetadata,
) -> list[
    dict[
        str,
        Any,
    ]
]:
    """
    Fixture 推荐使用 canonical full_name。

    为方便本地编写，也允许：

        canonical key 没有
        +
        base table key 唯一

    但最终仍然以 Metadata canonical identity 为准。
    """

    canonical = (
        metadata.full_name
        .strip()
        .lower()
    )

    if canonical in fixtures:

        return fixtures[
            canonical
        ]

    base_name = (
        canonical
        .rsplit(
            ".",
            1,
        )[-1]
    )

    if base_name in fixtures:

        return fixtures[
            base_name
        ]

    raise RuntimeError(
        (
            "Missing fixture declaration "
            f"for READ source "
            f"{canonical}. "
            "If this table should be empty, "
            "declare it explicitly as []."
        )
    )


# ============================================================
# Preview
# ============================================================


def _preview_target(
    *,
    simulator: MaxComputeLocalSimulator,
    table_name: str,
    limit: int,
) -> None:

    result = (
        simulator.query(
            (
                "SELECT * "
                f"FROM {table_name}"
            )
        )
    )

    print()
    print(
        "=" * 80
    )

    print(
        (
            "TARGET: "
            f"{table_name}"
        )
    )

    print(
        (
            "ROW COUNT: "
            f"{len(result.rows)}"
        )
    )

    print(
        (
            "COLUMNS: "
            + ", ".join(
                result.columns
            )
        )
    )

    print(
        "-" * 80
    )

    for row in (
        result.rows[
            :limit
        ]
    ):

        print(
            row
        )

    if (
        len(result.rows)
        > limit
    ):

        print(
            (
                "... "
                f"{len(result.rows) - limit} "
                "more rows"
            )
        )


# ============================================================
# Main
# ============================================================


def main() -> int:

    args = (
        _parse_args()
    )

    sql = (
        args.sql
        .read_text(
            encoding="utf-8",
        )
    )

    fixtures_raw = (
        _read_json(
            args.fixtures
        )
    )

    parameters_raw = (
        _read_json(
            args.parameters
        )
    )

    if not isinstance(
        fixtures_raw,
        dict,
    ):
        raise RuntimeError(
            (
                "fixtures JSON must "
                "be an object."
            )
        )

    if not isinstance(
        parameters_raw,
        dict,
    ):
        raise RuntimeError(
            (
                "parameters JSON must "
                "be an object."
            )
        )

    fixtures = {
        str(name)
        .strip()
        .lower(): rows

        for name, rows
        in fixtures_raw.items()
    }

    parameters = {
        str(name)
        .strip()
        .lower(): value

        for name, value
        in parameters_raw.items()
    }

    # --------------------------------------------------------
    # 1. Program Analysis
    # --------------------------------------------------------

    analysis = (
        ProgramAnalysisService()
        .analyze(
            sql
        )
    )

    if (
        analysis.status
        is ProgramAnalysisStatus.FAILED
        or analysis.program is None
    ):

        print(
            (
                "PROGRAM ANALYSIS FAILED:\n"
                f"{analysis.failure_reason}"
            ),
            file=sys.stderr,
        )

        return 2

    program = (
        analysis.program
    )

    read_tables = (
        _collect_read_tables(
            program
        )
    )

    write_tables = (
        _collect_write_tables(
            program
        )
    )

    print(
        (
            "Program analysis: "
            f"{analysis.status.value}"
        )
    )

    print(
        (
            "Statements: "
            f"{len(program.statements)}"
        )
    )

    print(
        (
            "CTEs: "
            f"{len(program.cte_nodes)}"
        )
    )

    print(
        (
            "Physical READ tables: "
            f"{len(read_tables)}"
        )
    )

    print(
        (
            "WRITE targets: "
            f"{len(write_tables)}"
        )
    )

    # --------------------------------------------------------
    # 2. Metadata
    # --------------------------------------------------------

    repository = (
        SQLiteMetadataRepository(
            args.metadata_db
        )
    )

    read_metadata = tuple(
        _resolve_metadata(
            repository,
            table_name,
        )
        for table_name
        in read_tables
    )

    write_metadata = tuple(
        _resolve_metadata(
            repository,
            table_name,
        )
        for table_name
        in write_tables
    )

    metadata_by_name = {
        metadata.full_name
        .strip()
        .lower(): metadata

        for metadata
        in (
            read_metadata
            + write_metadata
        )
    }

    # --------------------------------------------------------
    # 3. Simulator
    # --------------------------------------------------------

    try:

        with MaxComputeLocalSimulator() as mc:

            # ------------------------------------------------
            # Register all physical objects
            # ------------------------------------------------

            for metadata in (
                metadata_by_name.values()
            ):

                mc.register_table(
                    metadata
                )

            # ------------------------------------------------
            # Load all READ fixtures
            # ------------------------------------------------

            for metadata in (
                read_metadata
            ):

                rows = (
                    _find_fixture_rows(
                        fixtures=fixtures,
                        metadata=metadata,
                    )
                )

                mc.load_rows(
                    metadata.full_name,
                    rows,
                )

            # ------------------------------------------------
            # Execute the entire production Program
            # ------------------------------------------------

            print()
            print(
                "Executing production Program..."
            )

            results = (
                mc.execute(
                    sql,
                    parameters=parameters,
                )
            )

            print(
                (
                    "Execution completed. "
                    f"{len(results)} "
                    "business statements executed."
                )
            )

            # ------------------------------------------------
            # Preview all write targets
            # ------------------------------------------------

            for metadata in (
                write_metadata
            ):

                _preview_target(
                    simulator=mc,
                    table_name=(
                        metadata.full_name
                    ),
                    limit=(
                        args.preview_rows
                    ),
                )

    except (
        MaxComputeSimulationError,
        RuntimeError,
    ) as exc:

        print(
            (
                "\nPRIVATE BENCHMARK FAILED\n"
                f"{exc}"
            ),
            file=sys.stderr,
        )

        return 1

    print()
    print(
        "PRIVATE BENCHMARK PASSED"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )