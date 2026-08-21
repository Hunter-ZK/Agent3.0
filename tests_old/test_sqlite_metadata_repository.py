from openpyxl import Workbook

from sql_pilot_engine.metadata.ingestion.excel import (
    import_metadata_excel,
)

from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)

from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)


def build_metadata_database(
    tmp_path,
):

    excel_path = (
        tmp_path
        / "metadata.xlsx"
    )

    database_path = (
        tmp_path
        / "metadata.db"
    )

    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "每个表的字段"

    sheet.append(
        (
            "字段英文",
            "字段中文",
            "英文表名",
            "中文表名",
        )
    )

    sheet.append(
        (
            "loan_bal_rmb",
            "贷款余额",
            "dwd_hd_201_cldwdk",
            "绿色单位贷款明细宽表",
        )
    )

    sheet.append(
        (
            "fin_org_type_code",
            "机构类型代码",
            "dwd_hd_201_cldwdk",
            "绿色单位贷款明细宽表",
        )
    )

    sheet.append(
        (
            "loan_bal_rmb",
            "贷款余额",
            "dwd_hd_101_cldwdk",
            "科技贷款明细宽表",
        )
    )

    workbook.save(
        excel_path
    )

    import_metadata_excel(
        excel_path,

        database_path,

        snapshot_label="2026-05",
    )

    return database_path


def test_repository_can_lookup_table(
    tmp_path,
):

    database_path = (
        build_metadata_database(
            tmp_path
        )
    )

    repository = (
        SQLiteMetadataRepository(
            database_path
        )
    )

    result = repository.get_table(
        "dwd_hd_201_cldwdk"
    )

    assert (
        result.status
        == MetadataLookupStatus.FOUND
    )

    assert result.table is not None

    assert (
        result.table.get_column(
            "loan_bal_rmb"
        )
        is not None
    )


def test_repository_accepts_project_qualified_name(
    tmp_path,
):

    database_path = (
        build_metadata_database(
            tmp_path
        )
    )

    repository = (
        SQLiteMetadataRepository(
            database_path
        )
    )

    result = repository.get_table(
        (
            "odps_prd_dwd."
            "dwd_hd_201_cldwdk"
        )
    )

    assert (
        result.status
        == MetadataLookupStatus.FOUND
    )


def test_catalog_can_find_table(
    tmp_path,
):

    database_path = (
        build_metadata_database(
            tmp_path
        )
    )

    repository = (
        SQLiteMetadataRepository(
            database_path
        )
    )

    results = repository.find_tables(
        "绿色贷款"
    )

    assert len(results) == 1

    assert (
        results[0].full_name
        == "dwd_hd_201_cldwdk"
    )


def test_catalog_can_find_columns(
    tmp_path,
):

    database_path = (
        build_metadata_database(
            tmp_path
        )
    )

    repository = (
        SQLiteMetadataRepository(
            database_path
        )
    )

    results = repository.find_columns(
        "贷款余额"
    )

    assert len(results) == 2

    assert {
        result.table_full_name
        for result in results
    } == {
        "dwd_hd_201_cldwdk",
        "dwd_hd_101_cldwdk",
    }


def test_catalog_can_find_column_usages(
    tmp_path,
):

    database_path = (
        build_metadata_database(
            tmp_path
        )
    )

    repository = (
        SQLiteMetadataRepository(
            database_path
        )
    )

    results = (
        repository
        .find_column_usages(
            "loan_bal_rmb"
        )
    )

    assert len(results) == 2