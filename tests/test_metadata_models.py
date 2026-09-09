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


def _column(
    name: str,
    *,
    ordinal_position: int,
    data_type: str = "string",
    is_partition: bool = False,
) -> ColumnMetadata:
    return ColumnMetadata(
        name=name,
        technical=ColumnTechnicalMetadata(
            ordinal_position=ordinal_position,
            data_type=data_type,
            is_partition=is_partition,
        ),
        business=ColumnBusinessMetadata(),
        semantic=ColumnSemanticMetadata(),
        management=ColumnManagementMetadata(),
    )


def _table() -> TableMetadata:
    return TableMetadata(
        full_name=(
            "odps_prd_dwd.loan_detail"
        ),
        technical=TableTechnicalMetadata(
            project="odps_prd_dwd",
            table_name="loan_detail",
            partition_fields=("dt",),
            column_count=3,
        ),
        business=TableBusinessMetadata(
            description="贷款明细",
        ),
        operational=(
            TableOperationalMetadata()
        ),
        management=(
            TableManagementMetadata()
        ),
        columns={
            "customer_id": _column(
                "customer_id",
                ordinal_position=1,
            ),
            "amount": _column(
                "amount",
                ordinal_position=2,
                data_type="BIGINT",
            ),
            "dt": _column(
                "dt",
                ordinal_position=3,
                is_partition=True,
            ),
        },
    )


def test_physical_column_ref_is_normalized():
    ref = PhysicalColumnRef(
        table_full_name=(
            " ODPS_PRD_DWD.LOAN_DETAIL "
        ),
        column_name=" CUSTOMER_ID ",
    )

    assert (
        ref.table_full_name
        == "odps_prd_dwd.loan_detail"
    )

    assert (
        ref.column_name
        == "customer_id"
    )


def test_table_metadata_normalizes_identity():
    table = _table()

    assert (
        table.full_name
        == "odps_prd_dwd.loan_detail"
    )

    assert (
        table.technical.project
        == "odps_prd_dwd"
    )

    assert (
        table.technical.table_name
        == "loan_detail"
    )


def test_get_column_is_case_insensitive():
    table = _table()

    column = table.get_column(
        " CUSTOMER_ID "
    )

    assert column is not None

    assert (
        column.name
        == "customer_id"
    )


def test_data_type_is_normalized():
    table = _table()

    amount = table.get_column(
        "amount"
    )

    assert amount is not None

    assert (
        amount.technical.data_type
        == "bigint"
    )


def test_columns_mapping_is_read_only():
    table = _table()

    with pytest.raises(
        TypeError
    ):
        table.columns[
            "new_column"
        ] = _column(
            "new_column",
            ordinal_position=4,
        )


def test_full_name_must_match_project_and_table():
    with pytest.raises(
        ValueError
    ):
        TableMetadata(
            full_name=(
                "wrong_project.loan_detail"
            ),
            technical=(
                TableTechnicalMetadata(
                    project=(
                        "odps_prd_dwd"
                    ),
                    table_name=(
                        "loan_detail"
                    ),
                )
            ),
            business=(
                TableBusinessMetadata()
            ),
            operational=(
                TableOperationalMetadata()
            ),
            management=(
                TableManagementMetadata()
            ),
            columns={},
        )


def test_column_mapping_key_must_match_column_name():
    with pytest.raises(
        ValueError
    ):
        TableMetadata(
            full_name=(
                "odps_prd_dwd.loan_detail"
            ),
            technical=(
                TableTechnicalMetadata(
                    project=(
                        "odps_prd_dwd"
                    ),
                    table_name=(
                        "loan_detail"
                    ),
                )
            ),
            business=(
                TableBusinessMetadata()
            ),
            operational=(
                TableOperationalMetadata()
            ),
            management=(
                TableManagementMetadata()
            ),
            columns={
                "wrong_name": _column(
                    "customer_id",
                    ordinal_position=1,
                ),
            },
        )


def test_partition_field_must_exist():
    with pytest.raises(
        ValueError
    ):
        TableMetadata(
            full_name=(
                "odps_prd_dwd.loan_detail"
            ),
            technical=(
                TableTechnicalMetadata(
                    project=(
                        "odps_prd_dwd"
                    ),
                    table_name=(
                        "loan_detail"
                    ),
                    partition_fields=(
                        "dt",
                    ),
                )
            ),
            business=(
                TableBusinessMetadata()
            ),
            operational=(
                TableOperationalMetadata()
            ),
            management=(
                TableManagementMetadata()
            ),
            columns={
                "customer_id": _column(
                    "customer_id",
                    ordinal_position=1,
                ),
            },
        )


def test_column_count_must_match_loaded_columns():
    with pytest.raises(
        ValueError
    ):
        TableMetadata(
            full_name=(
                "odps_prd_dwd.loan_detail"
            ),
            technical=(
                TableTechnicalMetadata(
                    project=(
                        "odps_prd_dwd"
                    ),
                    table_name=(
                        "loan_detail"
                    ),
                    column_count=2,
                )
            ),
            business=(
                TableBusinessMetadata()
            ),
            operational=(
                TableOperationalMetadata()
            ),
            management=(
                TableManagementMetadata()
            ),
            columns={
                "customer_id": _column(
                    "customer_id",
                    ordinal_position=1,
                ),
            },
        )