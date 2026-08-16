from __future__ import annotations

from sql_pilot_engine.evaluation.models import (
    GoldenTextToSQLCase,
)


TEXT_TO_SQL_GOLDEN_V0_1 = (
    GoldenTextToSQLCase(
        case_id="order_amount_by_user",

        question=(
            "统计每个用户订单总金额"
        ),

        expected_tables=(
            "dwd_order_detail",
        ),

        expected_dimensions=(
            "user_id",
        ),

        expected_metrics=(
            "total_order_amount",
        ),

        expected_group_by=(
            "user_id",
        ),
    ),
)