from __future__ import annotations

import pytest

from sql_pilot_engine.context.semantic.models import (
    SemanticMetric,
    SemanticModel,
    SemanticTable,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.linking.schema_linker import (
    SchemaLinker,
    SchemaLinkingError,
)

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableLookupResult,
    TableMetadata,
)


class FakeMetadataProvider:

    def __init__(
        self,
        tables: dict[
            str,
            TableMetadata,
        ],
        *,
        fail: bool = False,
    ) -> None:

        self.tables = {
            name.lower(): table
            for name, table
            in tables.items()
        }

        self.fail = fail

    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:

        if self.fail:
            return (
                TableLookupResult
                .failed(
                    "metadata unavailable"
                )
            )

        normalized = (
            full_name
            .lower()
        )

        table = self.tables.get(
            normalized
        )

        if table is None:

            bare_name = (
                normalized
                .split(".")[-1]
            )

            for (
                stored_name,
                stored_table,
            ) in self.tables.items():

                if (
                    stored_name
                    .split(".")[-1]
                    == bare_name
                ):
                    table = stored_table
                    break

        if table is None:
            return (
                TableLookupResult
                .not_found()
            )

        return (
            TableLookupResult
            .found(
                table
            )
        )


def build_physical_table(
) -> TableMetadata:

    return TableMetadata(
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

            "fin_org_code": (
                ColumnMetadata(
                    name=(
                        "fin_org_code"
                    ),
                    data_type="STRING",
                    description=(
                        "金融机构代码"
                    ),
                )
            ),
        },
    )


def build_semantic_model(
) -> SemanticModel:

    return SemanticModel(
        tables=(
            SemanticTable(
                name=(
                    "ods_hd_100_cldkxx"
                ),
                description=(
                    "科技贷款明细宽表"
                ),
                columns=(),
            ),
        ),

        metrics=(
            SemanticMetric(
                name=(
                    "tech_loan_balance"
                ),
                description=(
                    "科技贷款余额"
                ),
                expression=(
                    "SUM(loan_bal_rmb)"
                ),
                table=(
                    "ods_hd_100_cldkxx"
                ),
            ),
        ),
    )


def build_plan(
) -> QueryPlan:

    return QueryPlan(
        tables=(
            "ods_hd_100_cldkxx",
        ),

        dimensions=(
            "fin_org_code",
        ),

        metrics=(
            "tech_loan_balance",
        ),

        group_by=(
            "fin_org_code",
        ),
    )


def build_linker(
    *,
    provider: FakeMetadataProvider,
) -> SchemaLinker:

    return SchemaLinker(
        metadata_provider=provider,
        semantic_model=(
            build_semantic_model()
        ),
    )


def test_schema_linker_resolves_plan_to_physical_schema():

    physical_table = (
        build_physical_table()
    )

    linker = build_linker(
        provider=(
            FakeMetadataProvider(
                {
                    physical_table
                    .full_name: (
                        physical_table
                    ),
                }
            )
        )
    )

    result = linker.link(
        plan=build_plan()
    )

    assert result.resolved is True

    assert (
        result.unresolved_terms
        == ()
    )

    assert (
        result.omitted_column_count
        == 0
    )

    assert (
        result.linking_confidence
        == 1.0
    )

    assert len(
        result.tables
    ) == 1

    linked_table = (
        result.tables[0]
        .metadata
    )

    assert (
        linked_table.full_name
        == (
            "odps_prd_dwd."
            "ods_hd_100_cldkxx"
        )
    )

    # F-25：
    # 当前阶段表级裁剪，
    # 表内字段必须完整保留。
    assert set(
        linked_table.columns
    ) == {
        "loan_bal_rmb",
        "dt",
        "fin_org_code",
    }


def test_schema_linker_reports_missing_physical_table():

    linker = build_linker(
        provider=(
            FakeMetadataProvider({})
        )
    )

    result = linker.link(
        plan=build_plan()
    )

    assert result.resolved is False

    assert (
        "ods_hd_100_cldkxx"
        in result.unresolved_terms
    )

    assert (
        result.linking_confidence
        < 1.0
    )


def test_schema_linker_reports_missing_metric():

    physical_table = (
        build_physical_table()
    )

    linker = build_linker(
        provider=(
            FakeMetadataProvider(
                {
                    physical_table
                    .full_name: (
                        physical_table
                    ),
                }
            )
        )
    )

    plan = QueryPlan(
        tables=(
            "ods_hd_100_cldkxx",
        ),

        dimensions=(),

        metrics=(
            "unknown_metric",
        ),
    )

    result = linker.link(
        plan=plan
    )

    assert result.resolved is False

    assert (
        "unknown_metric"
        in result.unresolved_terms
    )


def test_schema_linker_reports_metric_with_missing_physical_column():

    physical_table = (
        build_physical_table()
    )

    semantic_model = SemanticModel(
        tables=(),

        metrics=(
            SemanticMetric(
                name="bad_metric",
                description=(
                    "错误指标"
                ),
                expression=(
                    "SUM("
                    "missing_column"
                    ")"
                ),
                table=(
                    "ods_hd_100_cldkxx"
                ),
            ),
        ),
    )

    linker = SchemaLinker(
        metadata_provider=(
            FakeMetadataProvider(
                {
                    physical_table
                    .full_name: (
                        physical_table
                    ),
                }
            )
        ),

        semantic_model=(
            semantic_model
        ),
    )

    plan = QueryPlan(
        tables=(
            "ods_hd_100_cldkxx",
        ),
        dimensions=(),
        metrics=(
            "bad_metric",
        ),
    )

    result = linker.link(
        plan=plan
    )

    assert result.resolved is False

    assert (
        "bad_metric"
        in result.unresolved_terms
    )


def test_schema_linker_reports_missing_dimension():

    physical_table = (
        build_physical_table()
    )

    linker = build_linker(
        provider=(
            FakeMetadataProvider(
                {
                    physical_table
                    .full_name: (
                        physical_table
                    ),
                }
            )
        )
    )

    plan = QueryPlan(
        tables=(
            "ods_hd_100_cldkxx",
        ),

        dimensions=(
            "missing_dimension",
        ),

        metrics=(
            "tech_loan_balance",
        ),
    )

    result = linker.link(
        plan=plan
    )

    assert result.resolved is False

    assert (
        "missing_dimension"
        in result.unresolved_terms
    )


def test_schema_linker_propagates_metadata_system_error():

    linker = build_linker(
        provider=(
            FakeMetadataProvider(
                {},
                fail=True,
            )
        )
    )

    with pytest.raises(
        SchemaLinkingError,
        match=(
            "Metadata lookup failed"
        ),
    ):
        linker.link(
            plan=build_plan()
        )