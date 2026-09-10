from metadata_test_factory import (
    make_column_metadata,
    make_table_metadata,
)
import pytest

pytest.importorskip("pyspark")

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableMetadata,
)
from sql_pilot_engine.simulation import (
    MaxComputeLocalSimulator,
)


# ============================================================
# Shared Metadata
# ============================================================


def _fact_metadata() -> TableMetadata:
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
            "dt": make_column_metadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=(
            "dt",
        ),
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


def _summary_metadata() -> TableMetadata:
    return make_table_metadata(
        full_name="odps_prd_dws.sales_summary",
        columns={
            "customer_id": make_column_metadata(
                name="customer_id",
                data_type="string",
            ),
            "total_amount": make_column_metadata(
                name="total_amount",
                data_type="bigint",
            ),
            "dt": make_column_metadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=(
            "dt",
        ),
    )


def _tag_summary_metadata() -> TableMetadata:
    return make_table_metadata(
        full_name="odps_prd_dws.tag_summary",
        columns={
            "tag": make_column_metadata(
                name="tag",
                data_type="string",
            ),
            "cnt": make_column_metadata(
                name="cnt",
                data_type="bigint",
            ),
            "dt": make_column_metadata(
                name="dt",
                data_type="string",
            ),
        },
        partition_fields=(
            "dt",
        ),
    )


def _load_base_fixture(
    mc: MaxComputeLocalSimulator,
) -> None:

    mc.register_table(
        _fact_metadata()
    )

    mc.register_table(
        _customer_metadata()
    )

    mc.load_rows(
        "fact_sales",
        [
            {
                "customer_id": "c1",
                "region": "south",
                "product": "loan",
                "amount": 100,
                "tags": "a,b",
                "dt": "202609",
            },
            {
                "customer_id": "c1",
                "region": "south",
                "product": "loan",
                "amount": 200,
                "tags": "b,c",
                "dt": "202609",
            },
            {
                "customer_id": "c2",
                "region": "north",
                "product": "deposit",
                "amount": 50,
                "tags": "a",
                "dt": "202609",
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
        ],
    )


# ============================================================
# 1. CTE
# ============================================================


def test_maxcompute_cte_executes_directly():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        result = mc.query(
            """
            WITH base AS (
                SELECT
                    customer_id,
                    amount
                FROM fact_sales
                WHERE dt = '202609'
            ),
            summary AS (
                SELECT
                    customer_id,
                    SUM(amount) AS total_amount
                FROM base
                GROUP BY customer_id
            )
            SELECT
                customer_id,
                total_amount
            FROM summary
            ORDER BY customer_id
            """
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


# ============================================================
# 2. UNION ALL
# ============================================================


def test_maxcompute_union_all_executes_directly():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        result = mc.query(
            """
            SELECT
                customer_id,
                amount
            FROM fact_sales
            WHERE customer_id = 'c1'

            UNION ALL

            SELECT
                customer_id,
                amount
            FROM fact_sales
            WHERE customer_id = 'c2'

            ORDER BY
                customer_id,
                amount
            """
        )

        assert result.rows == (
            (
                "c1",
                100,
            ),
            (
                "c1",
                200,
            ),
            (
                "c2",
                50,
            ),
        )


# ============================================================
# 3. LATERAL VIEW + EXPLODE
# ============================================================


def test_maxcompute_lateral_view_executes_directly():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        result = mc.query(
            """
            SELECT
                tag,
                COUNT(*) AS cnt
            FROM fact_sales
            LATERAL VIEW
                EXPLODE(
                    SPLIT(tags, ',')
                ) exploded AS tag
            WHERE dt = '202609'
            GROUP BY tag
            ORDER BY tag
            """
        )

        assert result.rows == (
            (
                "a",
                2,
            ),
            (
                "b",
                2,
            ),
            (
                "c",
                1,
            ),
        )


# ============================================================
# 4. GROUPING SETS
# ============================================================


def test_maxcompute_grouping_sets_executes_directly():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        result = mc.query(
            """
            SELECT
                region,
                product,
                SUM(amount) AS total_amount
            FROM fact_sales
            WHERE dt = '202609'
            GROUP BY GROUPING SETS (
                (region, product),
                (region),
                ()
            )
            """
        )

        rows = set(
            result.rows
        )

        assert rows == {
            (
                "south",
                "loan",
                300,
            ),
            (
                "north",
                "deposit",
                50,
            ),
            (
                "south",
                None,
                300,
            ),
            (
                "north",
                None,
                50,
            ),
            (
                None,
                None,
                350,
            ),
        }


# ============================================================
# 5. MAPJOIN
# ============================================================


def test_maxcompute_mapjoin_executes_directly():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        result = mc.query(
            """
            SELECT /*+ MAPJOIN(d) */
                f.customer_id,
                d.customer_name,
                f.amount
            FROM fact_sales f
            LEFT JOIN dim_customer d
              ON f.customer_id = d.customer_id
            WHERE f.dt = '202609'
            ORDER BY
                f.customer_id,
                f.amount
            """
        )

        assert result.rows == (
            (
                "c1",
                "Alice",
                100,
            ),
            (
                "c1",
                "Alice",
                200,
            ),
            (
                "c2",
                "Bob",
                50,
            ),
        )


# ============================================================
# 6. DataWorks SET + Parameter
# ============================================================


def test_maxcompute_set_and_dataworks_parameter():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        result = mc.query(
            """
            SET odps.sql.type.system.odps2 = true;

            SELECT
                customer_id,
                SUM(amount) AS total_amount
            FROM fact_sales
            WHERE dt = '${p_month}'
            GROUP BY customer_id
            ORDER BY customer_id
            """,
            parameters={
                "p_month": "202609",
            },
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


# ============================================================
# 7. INSERT OVERWRITE + CTE + Static Partition
# ============================================================


def test_maxcompute_insert_overwrite_with_cte():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        mc.register_table(
            _summary_metadata()
        )

        mc.execute(
            """
            WITH base AS (
                SELECT
                    customer_id,
                    amount
                FROM fact_sales
                WHERE dt = '${p_month}'
            ),
            summary AS (
                SELECT
                    customer_id,
                    SUM(amount) AS total_amount
                FROM base
                GROUP BY customer_id
            )
            INSERT OVERWRITE TABLE sales_summary
            PARTITION(dt='${p_month}')
            SELECT
                customer_id,
                total_amount
            FROM summary
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
            FROM sales_summary
            ORDER BY customer_id
            """
        )

        assert result.rows == (
            (
                "c1",
                300,
                "202609",
            ),
            (
                "c2",
                50,
                "202609",
            ),
        )


# ============================================================
# 8. Multiple INSERT Statements
# ============================================================


def test_maxcompute_multiple_insert_statements():

    with MaxComputeLocalSimulator() as mc:

        _load_base_fixture(mc)

        mc.register_table(
            _summary_metadata()
        )

        mc.register_table(
            _tag_summary_metadata()
        )

        mc.execute(
            """
            INSERT OVERWRITE TABLE sales_summary
            PARTITION(dt='${p_month}')
            SELECT
                customer_id,
                SUM(amount) AS total_amount
            FROM fact_sales
            WHERE dt='${p_month}'
            GROUP BY customer_id
            ;

            INSERT OVERWRITE TABLE tag_summary
            PARTITION(dt='${p_month}')
            SELECT
                tag,
                COUNT(*) AS cnt
            FROM fact_sales
            LATERAL VIEW
                EXPLODE(
                    SPLIT(tags, ',')
                ) exploded AS tag
            WHERE dt='${p_month}'
            GROUP BY tag
            ;
            """,
            parameters={
                "p_month": "202609",
            },
        )

        sales = mc.query(
            """
            SELECT
                customer_id,
                total_amount
            FROM sales_summary
            ORDER BY customer_id
            """
        )

        tags = mc.query(
            """
            SELECT
                tag,
                cnt
            FROM tag_summary
            ORDER BY tag
            """
        )

        assert sales.rows == (
            (
                "c1",
                300,
            ),
            (
                "c2",
                50,
            ),
        )

        assert tags.rows == (
            (
                "a",
                2,
            ),
            (
                "b",
                2,
            ),
            (
                "c",
                1,
            ),
        )
        
        
def test_maxcompute_from_values_executes_directly():

    with MaxComputeLocalSimulator() as mc:

        result = mc.query(
            """
            SELECT
                group_order,
                group_code,
                group_name
            FROM VALUES
                (1, '01', 'first'),
                (2, '02', 'second'),
                (3, '03', 'third')
            AS t(
                group_order,
                group_code,
                group_name
            )
            ORDER BY group_order
            """
        )

        assert result.rows == (
            (
                1,
                "01",
                "first",
            ),
            (
                2,
                "02",
                "second",
            ),
            (
                3,
                "03",
                "third",
            ),
        )
        

def _dynamic_source_metadata() -> TableMetadata:

    return make_table_metadata(
        full_name=(
            "odps_prd_dwd.dynamic_source"
        ),
        columns={
            "customer_id": make_column_metadata(
                name="customer_id",
                data_type="string",
            ),
            "amount": make_column_metadata(
                name="amount",
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
        partition_fields=(
            "dt",
        ),
    )


def _dynamic_target_metadata() -> TableMetadata:

    return make_table_metadata(
        full_name=(
            "odps_prd_dws.dynamic_result"
        ),
        columns={
            "customer_id": make_column_metadata(
                name="customer_id",
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
        partition_fields=(
            "dt",
            "batch_num",
        ),
    )
    

def test_insert_overwrite_static_and_dynamic_partition():

    with MaxComputeLocalSimulator() as mc:

        mc.register_table(
            _dynamic_source_metadata()
        )

        mc.register_table(
            _dynamic_target_metadata()
        )

        mc.load_rows(
            "dynamic_source",
            [
                {
                    "customer_id": "c1",
                    "amount": 100,
                    "batch_num": "b1",
                    "dt": "202609",
                },
                {
                    "customer_id": "c1",
                    "amount": 200,
                    "batch_num": "b1",
                    "dt": "202609",
                },
                {
                    "customer_id": "c2",
                    "amount": 50,
                    "batch_num": "b2",
                    "dt": "202609",
                },
            ],
        )

        # 先给 target 放已有数据。
        #
        # 202609/b1 会被覆盖。
        # 202609/b3 不应被删除。
        # 202608/b1 也不应被删除。
        mc.load_rows(
            "dynamic_result",
            [
                {
                    "customer_id": "old1",
                    "total_amount": 999,
                    "batch_num": "b1",
                    "dt": "202609",
                },
                {
                    "customer_id": "old3",
                    "total_amount": 888,
                    "batch_num": "b3",
                    "dt": "202609",
                },
                {
                    "customer_id": "old_prev",
                    "total_amount": 777,
                    "batch_num": "b1",
                    "dt": "202608",
                },
            ],
        )

        mc.execute(
            """
            INSERT OVERWRITE TABLE dynamic_result
            PARTITION(
                dt='${p_month}',
                batch_num
            )
            SELECT
                customer_id,
                SUM(amount) AS total_amount,
                batch_num
            FROM dynamic_source
            WHERE dt='${p_month}'
            GROUP BY
                customer_id,
                batch_num
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
                batch_num,
                dt
            FROM dynamic_result
            ORDER BY
                dt,
                batch_num,
                customer_id
            """
        )

        assert result.rows == (
            (
                "old_prev",
                777,
                "b1",
                "202608",
            ),
            (
                "c1",
                300,
                "b1",
                "202609",
            ),
            (
                "c2",
                50,
                "b2",
                "202609",
            ),
            (
                "old3",
                888,
                "b3",
                "202609",
            ),
        )