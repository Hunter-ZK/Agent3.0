from __future__ import annotations

import sqlite3

import pytest
from openpyxl import Workbook

from sql_pilot_engine.metadata.ingestion.rebuild import rebuild_metadata_database
from sql_pilot_engine.metadata.schema import METADATA_SCHEMA_VERSION, MetadataProvenance
from sql_pilot_engine.metadata.sqlite_repository import SQLiteMetadataRepository


def _legacy_excel(tmp_path):
    source = tmp_path / "metadata.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "每个表的字段"
    sheet.append(["字段英文", "字段中文", "英文表名", "中文表名"])
    sheet.append(["customer_id", "客户编号", "loan_detail", "贷款明细"])
    sheet.append(["amount", "贷款金额", "loan_detail", "贷款明细"])
    workbook.save(source)
    workbook.close()
    return source


def test_rebuild_creates_atomic_runtime_database(tmp_path):
    source = _legacy_excel(tmp_path)
    database = tmp_path / "metadata.db"
    result = rebuild_metadata_database(
        metadata_source_path=source,
        database_path=database,
        metadata_source_label="unit-test",
    )
    assert result.schema_version == METADATA_SCHEMA_VERSION
    assert result.provenance is MetadataProvenance.PARTIAL
    assert database.exists()
    assert not (tmp_path / "metadata.db.building").exists()
    assert SQLiteMetadataRepository(database).get_table("loan_detail").table is not None


def test_rebuild_writes_build_provenance(tmp_path):
    source = _legacy_excel(tmp_path)
    database = tmp_path / "metadata.db"
    rebuild_metadata_database(
        metadata_source_path=source,
        database_path=database,
        metadata_source_label="2026-09",
    )
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT schema_version, provenance, source_ref,
                   metadata_source_name, metadata_source_label
            FROM metadata_build_info WHERE id = 1
            """
        ).fetchone()
    assert row == (
        METADATA_SCHEMA_VERSION,
        "PARTIAL",
        source.name,
        source.name,
        "2026-09",
    )


def test_failed_rebuild_does_not_replace_existing_database(tmp_path):
    database = tmp_path / "metadata.db"
    database.write_bytes(b"existing-database-marker")
    source = tmp_path / "invalid.xlsx"
    workbook = Workbook()
    workbook.active.append(["wrong", "headers"])
    workbook.save(source)
    workbook.close()
    with pytest.raises(ValueError):
        rebuild_metadata_database(metadata_source_path=source, database_path=database)
    assert database.read_bytes() == b"existing-database-marker"
    assert not (tmp_path / "metadata.db.building").exists()
