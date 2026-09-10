from __future__ import annotations

import pytest

from sql_pilot_engine.metadata.models import (
    ColumnBusinessMetadata,
    ColumnManagementMetadata,
    ColumnMetadata,
    ColumnSemanticMetadata,
    ColumnTechnicalMetadata,
    PhysicalColumnRef,
    TableBusinessMetadata,
    TableManagementMetadata,
    TableMetadata,
    TableOperationalMetadata,
    TableTechnicalMetadata,
)


def _column(name: str, ordinal: int, *, data_type: str = "string", partition: bool = False):
    return ColumnMetadata(
        name=name,
        technical=ColumnTechnicalMetadata(
            ordinal_position=ordinal,
            data_type=data_type,
            is_partition=partition,
        ),
        business=ColumnBusinessMetadata(),
        semantic=ColumnSemanticMetadata(),
        management=ColumnManagementMetadata(),
    )


def _table() -> TableMetadata:
    return TableMetadata(
        full_name="odps_prd_dwd.loan_detail",
        technical=TableTechnicalMetadata(
            project="odps_prd_dwd",
            table_name="loan_detail",
            partition_fields=("dt",),
            column_count=3,
        ),
        business=TableBusinessMetadata(description="贷款明细"),
        operational=TableOperationalMetadata(),
        management=TableManagementMetadata(),
        columns={
            "customer_id": _column("customer_id", 1),
            "amount": _column("amount", 2, data_type="BIGINT"),
            "dt": _column("dt", 3, partition=True),
        },
    )


def test_physical_column_ref_normalizes_identity():
    ref = PhysicalColumnRef(" ODPS_PRD_DWD.LOAN_DETAIL ", " CUSTOMER_ID ")
    assert ref.table_full_name == "odps_prd_dwd.loan_detail"
    assert ref.column_name == "customer_id"


def test_table_metadata_is_nested_and_normalized():
    table = _table()
    assert table.full_name == "odps_prd_dwd.loan_detail"
    assert table.technical.project == "odps_prd_dwd"
    assert table.business.description == "贷款明细"
    assert table.get_column(" AMOUNT ").technical.data_type == "bigint"


def test_columns_mapping_is_read_only():
    table = _table()
    with pytest.raises(TypeError):
        table.columns["new"] = _column("new", 4)


def test_full_name_must_match_technical_identity():
    with pytest.raises(ValueError, match="does not match technical identity"):
        TableMetadata(
            full_name="wrong.loan_detail",
            technical=TableTechnicalMetadata(
                project="odps_prd_dwd",
                table_name="loan_detail",
            ),
            business=TableBusinessMetadata(),
            operational=TableOperationalMetadata(),
            management=TableManagementMetadata(),
            columns={},
        )


def test_partition_field_must_exist_in_columns():
    with pytest.raises(ValueError, match="Partition fields are missing"):
        TableMetadata(
            full_name="loan_detail",
            technical=TableTechnicalMetadata(
                project="",
                table_name="loan_detail",
                partition_fields=("dt",),
            ),
            business=TableBusinessMetadata(),
            operational=TableOperationalMetadata(),
            management=TableManagementMetadata(),
            columns={"id": _column("id", 1)},
        )


def test_partial_metadata_may_represent_unknown_data_type():
    column = _column("amount", 1, data_type="")
    assert column.technical.data_type == ""
