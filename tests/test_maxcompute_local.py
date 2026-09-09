import pytest

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableMetadata,
)
from sql_pilot_engine.simulation import (
    MaxComputeLocalSimulator,
    MaxComputeSimulationError,
)


def _loan_metadata(
    full_name: str = (
        "odps_prd_dwd.loan_detail"
    ),
) -> TableMetadata:

    return TableMetadata(
        full_name=full_name,
        columns={
            "customer_id": ColumnMetadata(
                name="customer_id",
                data_type="string",
            ),
            "amount": ColumnMetadata(
                name="amount",
                data_type="bigint",
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


def _result_metadata() -> TableMetadata:

    return TableMetadata(
        full_name=(
            "odps_prd_dws.loan_result"
        ),
        columns={
            "customer_id": ColumnMetadata(
                name="customer_id",
                data_type="string",
            ),
            "total_amount": ColumnMetadata(
                name="total_amount",
                data_type="bigint",
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


def test_register_load_and_query():

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _loan_metadata()
        )

        mc.load_rows(
            "loan_detail",
            [
                {
                    "customer_id": "c1",
                    "amount": 100,
                    "dt": "202609",
                },
                {
                    "customer_id": "c1",
                    "amount": 200,
                    "dt": "202609",
                },
                {
                    "customer_id": "c2",
                    "amount": 50,
                    "dt": "202609",
                },
            ],
        )

        result = mc.query(
            """
            SELECT
                customer_id,
                SUM(amount) AS total_amount
            FROM loan_detail
            GROUP BY customer_id
            ORDER BY customer_id
            """
        )

        assert result.columns == (
            "customer_id",
            "total_amount",
        )

        assert result.rows == (
            (
                "c1",
                300,
            ),
            (
                "c2",
                50,
            ),
        )


def test_dataworks_parameter():

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _loan_metadata()
        )

        mc.load_rows(
            "loan_detail",
            [
                {
                    "customer_id": "c1",
                    "amount": 100,
                    "dt": "202609",
                },
                {
                    "customer_id": "c2",
                    "amount": 200,
                    "dt": "202608",
                },
            ],
        )

        result = mc.query(
            """
            SELECT
                customer_id
            FROM loan_detail
            WHERE dt='${p_month}'
            """,
            parameters={
                "p_month": "202609",
            },
        )

        assert result.rows == (
            (
                "c1",
            ),
        )


def test_insert_overwrite_static_partition():

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _loan_metadata()
        )

        mc.register_table(
            _result_metadata()
        )

        mc.load_rows(
            "loan_detail",
            [
                {
                    "customer_id": "c1",
                    "amount": 100,
                    "dt": "202609",
                },
                {
                    "customer_id": "c1",
                    "amount": 200,
                    "dt": "202609",
                },
            ],
        )

        mc.execute(
            """
            INSERT OVERWRITE TABLE loan_result
            PARTITION(dt='${p_month}')
            SELECT
                customer_id,
                SUM(amount) AS total_amount
            FROM loan_detail
            WHERE dt='${p_month}'
            GROUP BY customer_id
            """,
            parameters={
                "p_month": "202609",
            },
        )

        result = mc.query(
            """
            SELECT
                customer_id,
                total_amount,
                dt
            FROM loan_result
            ORDER BY customer_id
            """
        )

        assert result.rows == (
            (
                "c1",
                300,
                "202609",
            ),
        )


def test_unique_bare_table_is_resolved():

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _loan_metadata(
                "project_a.loan_detail"
            )
        )

        assert (
            mc.resolve_table(
                "loan_detail"
            )
            == "project_a.loan_detail"
        )


def test_duplicate_bare_table_is_rejected():

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _loan_metadata(
                "project_a.loan_detail"
            )
        )

        mc.register_table(
            _loan_metadata(
                "project_b.loan_detail"
            )
        )

        with pytest.raises(
            MaxComputeSimulationError,
            match="Ambiguous table name",
        ):
            mc.query(
                """
                SELECT customer_id
                FROM loan_detail
                """
            )


def test_unique_unqualified_column_is_resolved_by_spark():

    customer_metadata = (
        TableMetadata(
            full_name=(
                "odps_prd_dim.customer"
            ),
            columns={
                "customer_id": (
                    ColumnMetadata(
                        name="customer_id",
                        data_type="string",
                    )
                ),
                "customer_name": (
                    ColumnMetadata(
                        name="customer_name",
                        data_type="string",
                    )
                ),
            },
        )
    )

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _loan_metadata()
        )

        mc.register_table(
            customer_metadata
        )

        mc.load_rows(
            "loan_detail",
            [
                {
                    "customer_id": "c1",
                    "amount": 100,
                    "dt": "202609",
                },
            ],
        )

        mc.load_rows(
            "customer",
            [
                {
                    "customer_id": "c1",
                    "customer_name": "Alice",
                },
            ],
        )

        result = mc.query(
            """
            SELECT amount
            FROM loan_detail a
            JOIN customer b
              ON a.customer_id = b.customer_id
            """
        )

        assert result.rows == (
            (
                100,
            ),
        )


def test_duplicate_unqualified_column_is_rejected_by_spark():

    other_metadata = (
        TableMetadata(
            full_name=(
                "odps_prd_dws.other_loan"
            ),
            columns={
                "customer_id": (
                    ColumnMetadata(
                        name="customer_id",
                        data_type="string",
                    )
                ),
                "amount": (
                    ColumnMetadata(
                        name="amount",
                        data_type="bigint",
                    )
                ),
            },
        )
    )

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _loan_metadata()
        )

        mc.register_table(
            other_metadata
        )

        mc.load_rows(
            "loan_detail",
            [
                {
                    "customer_id": "c1",
                    "amount": 100,
                    "dt": "202609",
                },
            ],
        )

        mc.load_rows(
            "other_loan",
            [
                {
                    "customer_id": "c1",
                    "amount": 200,
                },
            ],
        )

        with pytest.raises(
            MaxComputeSimulationError,
        ) as exc_info:

            mc.query(
                """
                SELECT amount
                FROM loan_detail a
                JOIN other_loan b
                  ON a.customer_id = b.customer_id
                """
            )

        assert (
            "AMBIGUOUS"
            in str(
                exc_info.value
            ).upper()
        )