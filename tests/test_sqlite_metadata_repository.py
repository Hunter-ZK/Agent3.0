from __future__ import annotations

import sqlite3

from sql_pilot_engine.metadata.models import MetadataLookupStatus
from sql_pilot_engine.metadata.schema import (
    initialize_metadata_database,
    write_build_info,
)
from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)


def _repository(tmp_path, *table_names: str) -> SQLiteMetadataRepository:
    database_path = tmp_path / "metadata.db"
    initialize_metadata_database(database_path)

    with sqlite3.connect(database_path) as connection:
        write_build_info(connection, metadata_source_name="test")

        for table_name in table_names:
            connection.execute(
                """
                INSERT INTO metadata_table (
                    full_name,
                    description,
                    layer
                )
                VALUES (?, '', 'dwd')
                """,
                (table_name,),
            )

    return SQLiteMetadataRepository(database_path)


def test_get_table_requires_exact_canonical_identity(tmp_path):
    repository = _repository(
        tmp_path,
        "project_a.loan_detail",
    )

    assert (
        repository.get_table("project_a.loan_detail").status
        is MetadataLookupStatus.FOUND
    )

    assert (
        repository.get_table("loan_detail").status
        is MetadataLookupStatus.NOT_FOUND
    )


def test_find_table_identifiers_returns_unique_canonical_candidate(tmp_path):
    repository = _repository(
        tmp_path,
        "project_a.loan_detail",
    )

    matches = repository.find_table_identifiers("loan_detail")

    assert tuple(item.full_name for item in matches) == (
        "project_a.loan_detail",
    )


def test_find_table_identifiers_returns_all_ambiguous_candidates(tmp_path):
    repository = _repository(
        tmp_path,
        "project_a.loan_detail",
        "project_b.loan_detail",
    )

    matches = repository.find_table_identifiers("loan_detail")

    assert tuple(item.full_name for item in matches) == (
        "project_a.loan_detail",
        "project_b.loan_detail",
    )
