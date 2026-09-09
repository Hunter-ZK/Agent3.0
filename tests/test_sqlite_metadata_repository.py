from __future__ import annotations

import json
import sqlite3

from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)

from sql_pilot_engine.metadata.schema import (
    MetadataProvenance,
    initialize_metadata_database,
    write_build_info,
)

from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)


def _insert_table(
    connection: sqlite3.Connection,
    *,
    project: str,
    table_name: str,
    description: str = "",
) -> int:

    full_name = (
        f"{project}.{table_name}"
        if project
        else table_name
    )

    cursor = connection.execute(
        """
        INSERT INTO metadata_table (
            full_name,
            project,
            table_name,

            partition_fields_json,
            column_count,

            description,

            related_business_json,
            business_key_json
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            full_name,
            project,
            table_name,
            json.dumps(
                ["dt"]
            ),
            2,
            description,
            json.dumps(
                ["贷款业务"]
            ),
            json.dumps(
                ["customer_id"]
            ),
        ),
    )

    table_id = int(
        cursor.lastrowid
    )

    customer_cursor = (
        connection.execute(
            """
            INSERT INTO metadata_column (
                table_id,
                name,
                ordinal_position,
                data_type,
                nullable,
                is_partition,

                description,

                is_code_field,
                is_dimension,
                is_metric
            )
            VALUES (
                ?,
                'customer_id',
                1,
                'string',
                0,
                0,
                '客户编号',
                0,
                0,
                0
            )
            """,
            (
                table_id,
            ),
        )
    )

    customer_column_id = int(
        customer_cursor.lastrowid
    )

    connection.execute(
        """
        INSERT INTO metadata_column (
            table_id,
            name,
            ordinal_position,
            data_type,
            nullable,
            is_partition,

            description,

            is_code_field,
            is_dimension,
            is_metric
        )
        VALUES (
            ?,
            'dt',
            2,
            'string',
            0,
            1,
            '数据日期',
            0,
            0,
            0
        )
        """,
        (
            table_id,
        ),
    )

    connection.execute(
        """
        INSERT INTO metadata_table_upstream (
            table_id,
            upstream_full_name,
            ordinal_position
        )
        VALUES (
            ?,
            'odps_prd_ods.ods_customer',
            1
        )
        """,
        (
            table_id,
        ),
    )

    connection.execute(
        """
        INSERT INTO metadata_column_upstream (
            column_id,
            upstream_table_full_name,
            upstream_column_name,
            ordinal_position
        )
        VALUES (
            ?,
            'odps_prd_ods.ods_customer',
            'customer_id',
            1
        )
        """,
        (
            customer_column_id,
        ),
    )

    return table_id


def _repository(
    tmp_path,
    *tables: tuple[
        str,
        str,
    ],
) -> SQLiteMetadataRepository:

    database_path = (
        tmp_path
        / "metadata.db"
    )

    initialize_metadata_database(
        database_path
    )

    with sqlite3.connect(
        database_path
    ) as connection:

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        write_build_info(
            connection,
            metadata_source_name="test",
            metadata_source_label="unit-test",
            provenance=(
                MetadataProvenance
                .SYNTHETIC
            ),
            source_ref=(
                "tests/"
                "test_sqlite_metadata_repository.py"
            ),
        )

        for (
            project,
            table_name,
        ) in tables:

            _insert_table(
                connection,
                project=project,
                table_name=table_name,
                description=(
                    f"{table_name}测试表"
                ),
            )

    return SQLiteMetadataRepository(
        database_path
    )


def test_get_table_rebuilds_nested_metadata(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
    )

    result = repository.get_table(
        "project_a.loan_detail"
    )

    assert (
        result.status
        is MetadataLookupStatus.FOUND
    )

    assert result.table is not None

    table = result.table

    assert (
        table.full_name
        == "project_a.loan_detail"
    )

    assert (
        table.technical.project
        == "project_a"
    )

    assert (
        table.technical.table_name
        == "loan_detail"
    )

    assert (
        table.technical.partition_fields
        == ("dt",)
    )

    assert (
        table.technical.column_count
        == 2
    )

    assert (
        table.technical.declared_upstream_tables
        == (
            "odps_prd_ods.ods_customer",
        )
    )

    assert (
        table.business.description
        == "loan_detail测试表"
    )

    assert (
        table.business.related_business
        == (
            "贷款业务",
        )
    )

    assert (
        table.business.business_key
        == (
            "customer_id",
        )
    )


def test_get_table_rebuilds_column_metadata(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
    )

    result = repository.get_table(
        "project_a.loan_detail"
    )

    assert result.table is not None

    column = (
        result.table
        .get_column(
            "customer_id"
        )
    )

    assert column is not None

    assert (
        column.technical.data_type
        == "string"
    )

    assert (
        column.technical.nullable
        is False
    )

    assert (
        column.business.description
        == "客户编号"
    )

    assert (
        len(
            column
            .technical
            .declared_upstream_columns
        )
        == 1
    )

    upstream = (
        column
        .technical
        .declared_upstream_columns[
            0
        ]
    )

    assert (
        upstream.table_full_name
        == "odps_prd_ods.ods_customer"
    )

    assert (
        upstream.column_name
        == "customer_id"
    )


def test_get_table_requires_exact_canonical_identity(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
    )

    assert (
        repository
        .get_table(
            "project_a.loan_detail"
        )
        .status
        is MetadataLookupStatus.FOUND
    )

    assert (
        repository
        .get_table(
            "loan_detail"
        )
        .status
        is MetadataLookupStatus.NOT_FOUND
    )


def test_find_table_identifiers_returns_unique_candidate(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
    )

    matches = (
        repository
        .find_table_identifiers(
            "loan_detail"
        )
    )

    assert tuple(
        item.full_name
        for item
        in matches
    ) == (
        "project_a.loan_detail",
    )


def test_find_table_identifiers_returns_all_ambiguous_candidates(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
        (
            "project_b",
            "loan_detail",
        ),
    )

    matches = (
        repository
        .find_table_identifiers(
            "loan_detail"
        )
    )

    assert tuple(
        item.full_name
        for item
        in matches
    ) == (
        "project_a.loan_detail",
        "project_b.loan_detail",
    )


def test_find_table_identifiers_accepts_qualified_identity(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
        (
            "project_b",
            "loan_detail",
        ),
    )

    matches = (
        repository
        .find_table_identifiers(
            "project_a.loan_detail"
        )
    )

    assert tuple(
        item.full_name
        for item
        in matches
    ) == (
        "project_a.loan_detail",
    )


def test_find_column_usages_returns_all_exact_usages(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
        (
            "project_b",
            "loan_detail",
        ),
    )

    matches = (
        repository
        .find_column_usages(
            "customer_id"
        )
    )

    assert tuple(
        item.table_full_name
        for item
        in matches
    ) == (
        "project_a.loan_detail",
        "project_b.loan_detail",
    )


def test_repository_returns_not_found_for_unknown_table(
    tmp_path,
):
    repository = _repository(
        tmp_path,
        (
            "project_a",
            "loan_detail",
        ),
    )

    result = repository.get_table(
        "project_a.unknown"
    )

    assert (
        result.status
        is MetadataLookupStatus.NOT_FOUND
    )

    assert result.table is None


def test_repository_reports_schema_version_mismatch(
    tmp_path,
):
    database_path = (
        tmp_path
        / "metadata.db"
    )

    initialize_metadata_database(
        database_path
    )

    with sqlite3.connect(
        database_path
    ) as connection:

        connection.execute(
            """
            INSERT INTO metadata_build_info (
                id,
                schema_version,
                provenance,
                source_ref,
                metadata_source_name
            )
            VALUES (
                1,
                999,
                'SYNTHETIC',
                'test',
                'test'
            )
            """
        )

    repository = (
        SQLiteMetadataRepository(
            database_path
        )
    )

    result = repository.get_table(
        "project_a.loan_detail"
    )

    assert (
        result.status
        is MetadataLookupStatus.ERROR
    )

    assert (
        result.error_message
        is not None
    )

    assert (
        "schema version"
        in result.error_message.lower()
    )

