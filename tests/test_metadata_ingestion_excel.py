from __future__ import annotations

import sqlite3

import pytest
from openpyxl import Workbook

from sql_pilot_engine.metadata.ingestion.excel import LEGACY_FORMAT_NAME, import_metadata_excel
from sql_pilot_engine.metadata.models import MetadataLookupStatus
from sql_pilot_engine.metadata.schema import (
    MetadataProvenance,
    initialize_metadata_database,
    write_build_info,
)
from sql_pilot_engine.metadata.sqlite_repository import SQLiteMetadataRepository


def _legacy_excel(tmp_path):
    source = tmp_path / "legacy_metadata.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "每个表的字段"
    sheet.append(["字段英文", "字段中文", "英文表名", "中文表名"])
    sheet.append(["customer_id", "客户编号", "dwd_loan_detail", "贷款明细"])
    sheet.append(["amount", "贷款金额", "dwd_loan_detail", "贷款明细"])
    sheet.append(["amount", "贷款金额", "dwd_loan_detail", "贷款明细"])
    sheet.append(["", "无效字段", "dwd_loan_detail", "贷款明细"])
    workbook.save(source)
    workbook.close()
    return source


def test_legacy_excel_imports_as_partial_metadata(tmp_path):
    source = _legacy_excel(tmp_path)
    database = tmp_path / "metadata.db"
    initialize_metadata_database(database)
    result = import_metadata_excel(source, database)
    assert result.provenance is MetadataProvenance.PARTIAL
    assert result.source_format == LEGACY_FORMAT_NAME
    assert (result.table_count, result.column_count) == (1, 2)
    assert (result.raw_rows, result.accepted_rows, result.duplicate_rows, result.skipped_rows) == (4, 2, 1, 1)

    with sqlite3.connect(database) as connection:
        write_build_info(
            connection,
            metadata_source_name=source.name,
            provenance=result.provenance,
            source_ref=source.name,
        )
    lookup = SQLiteMetadataRepository(database).get_table("dwd_loan_detail")
    assert lookup.status is MetadataLookupStatus.FOUND
    assert lookup.table is not None
    assert lookup.table.technical.project == ""
    assert lookup.table.get_column("amount").technical.data_type == ""


def test_unknown_excel_format_is_rejected(tmp_path):
    source = tmp_path / "unknown.xlsx"
    workbook = Workbook()
    workbook.active.append(["foo", "bar"])
    workbook.save(source)
    workbook.close()
    database = tmp_path / "metadata.db"
    initialize_metadata_database(database)
    with pytest.raises(ValueError, match="Unsupported metadata Excel format"):
        import_metadata_excel(source, database)
