from __future__ import annotations

import sqlite3

from metadata_test_factory import make_column_metadata, make_table_metadata
from sql_pilot_engine.metadata.ingestion.writer import write_metadata_tables
from sql_pilot_engine.metadata.models import MetadataLookupStatus, PhysicalColumnRef
from sql_pilot_engine.metadata.schema import (
    MetadataProvenance,
    initialize_metadata_database,
    write_build_info,
)
from sql_pilot_engine.metadata.sqlite_repository import SQLiteMetadataRepository


def _repository(tmp_path, *tables):
    database = tmp_path / "metadata.db"
    initialize_metadata_database(database)
    with sqlite3.connect(database) as connection:
        write_metadata_tables(connection, tables)
        write_build_info(
            connection,
            metadata_source_name="test",
            provenance=MetadataProvenance.SYNTHETIC,
            source_ref="unit-test",
        )
    return SQLiteMetadataRepository(database)


def test_get_table_rebuilds_nested_metadata(tmp_path):
    table = make_table_metadata(
        "project_a.loan_detail",
        columns={
            "customer_id": make_column_metadata("customer_id", "string", False, "客户编号"),
            "dt": make_column_metadata("dt", "string", False, "数据日期", is_partition=True),
        },
        partition_fields=("dt",),
        description="贷款明细",
    )
    repository = _repository(tmp_path, table)
    result = repository.get_table("project_a.loan_detail")
    assert result.status is MetadataLookupStatus.FOUND
    assert result.table is not None
    assert result.table.technical.project == "project_a"
    assert result.table.business.description == "贷款明细"
    assert result.table.technical.partition_fields == ("dt",)


def test_get_table_rebuilds_declared_column_lineage(tmp_path):
    source = make_column_metadata("customer_id", "string")
    source = source.__class__(
        name=source.name,
        technical=source.technical.__class__(
            ordinal_position=1,
            data_type="string",
            declared_upstream_columns=(
                PhysicalColumnRef("ods.customer", "customer_id"),
            ),
        ),
        business=source.business,
        semantic=source.semantic,
        management=source.management,
    )
    table = make_table_metadata("dwd.loan_detail", columns={"customer_id": source})
    repository = _repository(tmp_path, table)
    result = repository.get_table("dwd.loan_detail")
    assert result.table is not None
    refs = result.table.get_column("customer_id").technical.declared_upstream_columns
    assert refs == (PhysicalColumnRef("ods.customer", "customer_id"),)


def test_get_table_is_exact_only(tmp_path):
    repository = _repository(
        tmp_path,
        make_table_metadata(
            "project_a.loan_detail",
            columns={"id": make_column_metadata("id")},
        ),
    )
    assert repository.get_table("loan_detail").status is MetadataLookupStatus.NOT_FOUND


def test_find_table_identifiers_returns_all_exact_candidates(tmp_path):
    repository = _repository(
        tmp_path,
        make_table_metadata("project_a.loan_detail", columns={"id": make_column_metadata("id")}),
        make_table_metadata("project_b.loan_detail", columns={"id": make_column_metadata("id")}),
    )
    assert tuple(
        item.full_name for item in repository.find_table_identifiers("loan_detail")
    ) == ("project_a.loan_detail", "project_b.loan_detail")


def test_find_column_usages_is_complete_fact_query(tmp_path):
    repository = _repository(
        tmp_path,
        make_table_metadata("project_a.loan_detail", columns={"id": make_column_metadata("id")}),
        make_table_metadata("project_b.loan_detail", columns={"id": make_column_metadata("id")}),
    )
    assert tuple(
        item.table_full_name for item in repository.find_column_usages("id")
    ) == ("project_a.loan_detail", "project_b.loan_detail")
