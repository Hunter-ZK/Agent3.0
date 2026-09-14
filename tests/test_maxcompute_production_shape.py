from pathlib import Path

import pytest

from metadata_test_factory import make_column_metadata, make_table_metadata
from sql_pilot_engine.metadata.models import TableMetadata
from sql_pilot_engine.simulation import MaxComputeLocalSimulator


pytest.importorskip("pyspark")

FIXTURE_SQL = (
    Path(__file__).parent
    / "fixtures"
    / "simulation"
    / "maxcompute_production_shape.sql"
)


def _fact_sales_metadata() -> TableMetadata:
    return make_table_metadata(
        full_name="odps_prd_dwd.fact_sales",
        columns={
            "customer_id": make_column_metadata(
                name="customer_id",
                data_type="string",
            ),
            "region": make_column_metadata(
                name="region",
                data_type="string",
            ),
            "product": make_column_metadata(
                name="product",
                data_type="string",
            ),
            "amount": make_column_metadata(
                name="amount",
                data_type="bigint",
            ),
            "tags": make_column_metadata(
                name="tags",
                data_type="string",
            ),
            "batch_num": make_column_metadata(
                name="batch_num",
                data_type="string",
            ),
            "dt": make_column_metadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=("dt",),
    )


def _customer_metadata() -> TableMetadata:
    return make_table_metadata(
        full_name="odps_prd_dim.dim_customer",
        columns={
            "customer_id": make_column_metadata(
                name="customer_id",
                data_type="string",
            ),
            "customer_name": make_column_metadata(
                name="customer_name",
                data_type="string",
            ),
        },
    )


def _production_result_metadata() -> TableMetadata:
    return make_table_metadata(
        full_name="odps_prd_dws.production_result",
        columns={
            "region": make_column_metadata(
                name="region",
                data_type="string",
            ),
            "product": make_column_metadata(
                name="product",
                data_type="string",
            ),
            "total_amount": make_column_metadata(
                name="total_amount",
                data_type="bigint",
            ),
            "batch_num": make_column_metadata(
                name="batch_num",
                data_type="string",
            ),
            "dt": make_column_metadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=("dt", "batch_num"),
    )


def _production_tag_result_metadata() -> TableMetadata:
    return make_table_metadata(
        full_name="odps_prd_dws.production_tag_result",
        columns={
            "tag": make_column_metadata(
                name="tag",
                data_type="string",
            ),
            "cnt": make_column_metadata(
                name="cnt",
                data_type="bigint",
            ),
            "batch_num": make_column_metadata(
                name="batch_num",
                data_type="string",
            ),
            "dt": make_column_metadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=("dt", "batch_num"),
    )


def _load_fixture(mc: MaxComputeLocalSimulator) -> None:
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
                # Previous-period row: proves ${p_month} filtering is applied.
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
            {"customer_id": "c1", "customer_name": "Alice"},
            {"customer_id": "c2", "customer_name": "Bob"},
            {"customer_id": "c3", "customer_name": "Carol"},
        ],
    )


def test_production_shape_program_executes_end_to_end() -> None:
    sql = FIXTURE_SQL.read_text(encoding="utf-8")

    with MaxComputeLocalSimulator() as mc:
        mc.register_table(_fact_sales_metadata())
        mc.register_table(_customer_metadata())
        mc.register_table(_production_result_metadata())
        mc.register_table(_production_tag_result_metadata())
        _load_fixture(mc)

        statement_results = mc.execute(
            sql,
            parameters={"p_month": "202609"},
        )
        assert len(statement_results) == 2

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

        # The production-shape SQL intentionally aggregates after LATERAL VIEW
        # EXPLODE. Each south/loan input row has two tags, so the two amount
        # values contribute twice: 100*2 + 200*2 = 600. This is the actual SQL
        # semantics and is separate from the second target's explicit tag count.
        assert set(production_result.rows) == {
            ("south", "loan", 600, "b1", "202609"),
            ("south", "ALL", 600, "b1", "202609"),
            ("ALL", "ALL", 600, "b1", "202609"),
            ("north", "deposit", 50, "b2", "202609"),
            ("north", "ALL", 50, "b2", "202609"),
            ("ALL", "ALL", 50, "b2", "202609"),
        }

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

        assert set(tag_result.rows) == {
            ("a", 1, "b1", "202609"),
            ("b", 2, "b1", "202609"),
            ("c", 1, "b1", "202609"),
            ("a", 1, "b2", "202609"),
        }
