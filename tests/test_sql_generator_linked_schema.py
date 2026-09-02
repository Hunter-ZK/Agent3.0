from __future__ import annotations

import pytest

from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
    LinkedTable,
)

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableMetadata,
)


class RecordingModel:

    def __init__(
        self,
    ) -> None:
        self.prompt: str | None = None

    def generate(
        self,
        prompt: str,
    ) -> str:

        self.prompt = prompt

        return (
            "SELECT SUM(loan_bal_rmb) "
            "FROM "
            "odps_prd_dwd."
            "ods_hd_100_cldkxx"
        )


def build_linked_schema(
) -> LinkedSchema:

    table = TableMetadata(
        full_name=(
            "odps_prd_dwd."
            "ods_hd_100_cldkxx"
        ),

        description=(
            "科技贷款明细宽表"
        ),

        columns={
            "loan_bal_rmb": (
                ColumnMetadata(
                    name=(
                        "loan_bal_rmb"
                    ),
                    data_type=(
                        "DECIMAL(22,2)"
                    ),
                    description=(
                        "贷款余额"
                    ),
                )
            ),

            "dt": (
                ColumnMetadata(
                    name="dt",
                    data_type="STRING",
                    description=(
                        "数据日期"
                    ),
                )
            ),
        },
    )

    return LinkedSchema(
        tables=(
            LinkedTable(
                metadata=table
            ),
        ),
    )


def build_context():

    return (
        QueryContextBuilder()
        .build(
            question=(
                "统计科技贷款余额"
            ),
            semantic_context=(
                "METRIC tech_loan_balance"
            ),
            business_knowledge=(),
            verified_sql=(),
            session_context=(),
        )
    )


def test_generator_receives_full_physical_schema():

    model = RecordingModel()

    generator = SQLGenerator(
        model=model
    )

    result = generator.generate(
        plan=QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),
            dimensions=(),
            metrics=(
                "tech_loan_balance",
            ),
        ),

        linked_schema=(
            build_linked_schema()
        ),

        query_context=(
            build_context()
        ),

        dialect="maxcompute",
    )

    assert result.sql

    assert model.prompt is not None

    assert (
        "odps_prd_dwd."
        "ods_hd_100_cldkxx"
        in model.prompt
    )

    assert (
        "loan_bal_rmb"
        in model.prompt
    )

    assert (
        "dt"
        in model.prompt
    )

