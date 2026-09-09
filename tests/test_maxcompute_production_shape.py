from pathlib import Path

import pytest

pytest.importorskip("pyspark")

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableMetadata,
)
from sql_pilot_engine.simulation import (
    MaxComputeLocalSimulator,
)


FIXTURE_SQL = (
    Path(__file__).parent
    / "fixtures"
    / "simulation"
    / "maxcompute_production_shape.sql"
)


# ============================================================
# Metadata
# ============================================================


def _fact_sales_metadata() -> TableMetadata:

    return TableMetadata(
        full_name=(
            "odps_prd_dwd.fact_sales"
        ),
        columns={
            "customer_id": ColumnMetadata(
                name="customer_id",
                data_type="string",
            ),
            "region": ColumnMetadata(
                name="region",
                data_type="string",
            ),
            "product": ColumnMetadata(
                name="product",
                data_type="string",
            ),
            "amount": ColumnMetadata(
                name="amount",
                data_type="bigint",
            ),
            "tags": ColumnMetadata(
                name="tags",
                data_type="string",
            ),
            "batch_num": ColumnMetadata(
                name="batch_num",
                data_type="string",
            ),
            "dt": ColumnMetadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=(
            "dt",
        ),
    )


def _customer_metadata() -> TableMetadata:

    return TableMetadata(
        full_name=(
            "odps_prd_dim.dim_customer"
        ),
        columns={
            "customer_id": ColumnMetadata(
                name="customer_id",
                data_type="string",
            ),
            "customer_name": ColumnMetadata(
                name="customer_name",
                data_type="string",
            ),
        },
    )


def _production_result_metadata() -> TableMetadata:

    return TableMetadata(
        full_name=(
            "odps_prd_dws.production_result"
        ),
        columns={
            "region": ColumnMetadata(
                name="region",
                data_type="string",
            ),
            "product": ColumnMetadata(
                name="product",
                data_type="string",
            ),
            "total_amount": ColumnMetadata(
                name="total_amount",
                data_type="bigint",
            ),
            "batch_num": ColumnMetadata(
                name="batch_num",
                data_type="string",
            ),
            "dt": ColumnMetadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=(
            "dt",
            "batch_num",
        ),
    )


def _production_tag_result_metadata() -> TableMetadata:

    return TableMetadata(
        full_name=(
            "odps_prd_dws.production_tag_result"
        ),
        columns={
            "tag": ColumnMetadata(
                name="tag",
                data_type="string",
            ),
            "cnt": ColumnMetadata(
                name="cnt",
                data_type="bigint",
            ),
            "batch_num": ColumnMetadata(
                name="batch_num",
                data_type="string",
            ),
            "dt": ColumnMetadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=(
            "dt",
            "batch_num",
        ),
    )


# ============================================================
# Fixture
# ============================================================


def _load_fixture(
    mc: MaxComputeLocalSimulator,
) -> None:

    mc.load_rows(
        "fact_sales",
        [
            {
                "customer_id": "c1",
                "region": "south",
                "product": "loan",
                "amount": 100,
                "tags": "a,b",
                "batch_num": "b1",
                "dt": "202609",
            },
            {
                "customer_id": "c1",
                "region": "south",
                "product": "loan",
                "amount": 200,
                "tags": "b,c",
                "batch_num": "b1",
                "dt": "202609",
            },
            {
                "customer_id": "c2",
                "region": "north",
                "product": "deposit",
                "amount": 50,
                "tags": "a",
                "batch_num": "b2",
                "dt": "202609",
            },
            {
                # 故意加入上期数据。
                # 用来证明 ${p_month} filter 生效。
                "customer_id": "c3",
                "region": "west",
                "product": "loan",
                "amount": 999,
                "tags": "x",
                "batch_num": "b1",
                "dt": "202608",
            },
        ],
    )

    mc.load_rows(
        "dim_customer",
        [
            {
                "customer_id": "c1",
                "customer_name": "Alice",
            },
            {
                "customer_id": "c2",
                "customer_name": "Bob",
            },
            {
                "customer_id": "c3",
                "customer_name": "Carol",
            },
        ],
    )


# ============================================================
# Production-shape Gate
# ============================================================


def test_production_shape_program_executes_end_to_end():

    sql = FIXTURE_SQL.read_text(
        encoding="utf-8",
    )

    with MaxComputeLocalSimulator() as mc:

        # --------------------------------------------------
        # Register authoritative Metadata
        # --------------------------------------------------

        mc.register_table(
            _fact_sales_metadata()
        )

        mc.register_table(
            _customer_metadata()
        )

        mc.register_table(
            _production_result_metadata()
        )

        mc.register_table(
            _production_tag_result_metadata()
        )

        # --------------------------------------------------
        # Load fixtures
        # --------------------------------------------------

        _load_fixture(mc)

        # --------------------------------------------------
        # Execute the complete two-INSERT Program
        # --------------------------------------------------

        statement_results = mc.execute(
            sql,
            parameters={
                "p_month": "202609",
            },
        )

        assert len(
            statement_results
        ) == 2

        # --------------------------------------------------
        # Validate target 1
        # --------------------------------------------------

        production_result = mc.query(
            """
            SELECT
                region,
                product,
                total_amount,
                batch_num,
                dt
            FROM production_result
            """
        )

        assert set(
            production_result.rows
        ) == {
            (
                "south",
                "loan",
                300,
                "b1",
                "202609",
            ),
            (
                "south",
                "ALL",
                300,
                "b1",
                "202609",
            ),
            (
                "ALL",
                "ALL",
                300,
                "b1",
                "202609",
            ),
            (
                "north",
                "deposit",
                50,
                "b2",
                "202609",
            ),
            (
                "north",
                "ALL",
                50,
                "b2",
                "202609",
            ),
            (
                "ALL",
                "ALL",
                50,
                "b2",
                "202609",
            ),
        }

        # --------------------------------------------------
        # Validate target 2
        # --------------------------------------------------

        tag_result = mc.query(
            """
            SELECT
                tag,
                cnt,
                batch_num,
                dt
            FROM production_tag_result
            """
        )

        assert set(
            tag_result.rows
        ) == {
            (
                "a",
                1,
                "b1",
                "202609",
            ),
            (
                "b",
                2,
                "b1",
                "202609",
            ),
            (
                "c",
                1,
                "b1",
                "202609",
            ),
            (
                "a",
                1,
                "b2",
                "202609",
            ),
        }