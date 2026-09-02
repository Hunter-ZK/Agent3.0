from __future__ import annotations

from sql_pilot_engine.context.semantic.models import (
    SemanticFilter,
    SemanticMetric,
    SemanticModel,
)

from sql_pilot_engine.generation.metric_compiler import (
    MetricSQLCompiler,
)

from sql_pilot_engine.generation.models import (
    CompilationFallbackReason,
    CompilationStatus,
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
    LinkedTable,
    SchemaBinding,
    SchemaBindingKind,
)

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableMetadata,
)


TABLE_NAME = (
    "odps_prd_dwd."
    "ods_hd_100_cldkxx"
)


def _table() -> TableMetadata:

    return TableMetadata(
        full_name=TABLE_NAME,

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

            "ent_code": (
                ColumnMetadata(
                    name="ent_code",

                    data_type="STRING",

                    description=(
                        "企业代码"
                    ),
                )
            ),

            "dt": (
                ColumnMetadata(
                    name="dt",

                    data_type="STRING",

                    description="统计期",
                )
            ),

            (
                "is_high_tech_"
                "mfg_loan_code"
            ): (
                ColumnMetadata(
                    name=(
                        "is_high_tech_"
                        "mfg_loan_code"
                    ),

                    data_type="STRING",

                    description=(
                        "高新技术企业标识"
                    ),
                )
            ),

            "region_code": (
                ColumnMetadata(
                    name="region_code",

                    data_type="STRING",

                    description="地区",
                )
            ),
        },
    )


def _balance_metric(
) -> SemanticMetric:

    return SemanticMetric(
        name=(
            "tech_loan_balance"
        ),

        description=(
            "科技贷款余额"
        ),

        expression=(
            "SUM(loan_bal_rmb)"
        ),

        table=TABLE_NAME,

        aggregation="sum",

        source_column=(
            "loan_bal_rmb"
        ),

        fixed_filters=(
            SemanticFilter(
                column=(
                    "is_high_tech_"
                    "mfg_loan_code"
                ),

                operator="=",

                value="1",
            ),
        ),
    )


def _count_metric(
) -> SemanticMetric:

    return SemanticMetric(
        name=(
            "enterprise_count"
        ),

        description="获贷企业数",

        expression=(
            "COUNT(DISTINCT ent_code)"
        ),

        table=TABLE_NAME,

        aggregation=(
            "count_distinct"
        ),

        source_column=(
            "ent_code"
        ),
    )


def _complex_metric(
) -> SemanticMetric:

    return SemanticMetric(
        name="weighted_rate",

        description=(
            "加权利率"
        ),

        expression=(
            "SUM(loan_bal_rmb * rate)"
            " / SUM(loan_bal_rmb)"
        ),

        table=TABLE_NAME,

        aggregation=None,

        source_column=None,
    )


def _semantic_model(
    *metrics,
) -> SemanticModel:

    return SemanticModel(
        tables=(),

        metrics=tuple(
            metrics
        ),
    )


def _linked_schema(
    *,
    include_region: bool = False,
) -> LinkedSchema:

    bindings = [
        SchemaBinding(
            kind=(
                SchemaBindingKind.TABLE
            ),

            logical_name=(
                "ods_hd_100_cldkxx"
            ),

            physical_table=(
                TABLE_NAME
            ),
        ),

        SchemaBinding(
            kind=(
                SchemaBindingKind.METRIC
            ),

            logical_name=(
                "tech_loan_balance"
            ),

            physical_table=(
                TABLE_NAME
            ),

            physical_columns=(
                "loan_bal_rmb",
            ),
        ),

        SchemaBinding(
            kind=(
                SchemaBindingKind.METRIC
            ),

            logical_name=(
                "enterprise_count"
            ),

            physical_table=(
                TABLE_NAME
            ),

            physical_columns=(
                "ent_code",
            ),
        ),
    ]

    if include_region:

        bindings.append(
            SchemaBinding(
                kind=(
                    SchemaBindingKind.COLUMN
                ),

                logical_name=(
                    "region_code"
                ),

                physical_table=(
                    TABLE_NAME
                ),

                physical_columns=(
                    "region_code",
                ),
            )
        )

    return LinkedSchema(
        tables=(
            LinkedTable(
                metadata=_table()
            ),
        ),

        bindings=tuple(
            bindings
        ),
    )


def test_simple_metric_is_compiled():

    compiler = MetricSQLCompiler(
        semantic_model=(
            _semantic_model(
                _balance_metric()
            )
        )
    )

    outcome = compiler.compile(
        plan=QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),

            dimensions=(),

            metrics=(
                "tech_loan_balance",
            ),

            filters=(
                "dt = '202607'",
            ),

            group_by=(),
        ),

        linked_schema=(
            _linked_schema()
        ),

        dialect="maxcompute",
    )

    assert (
        outcome.status
        is CompilationStatus.COMPILED
    )

    assert (
        outcome.generated_sql
        is not None
    )

    sql = (
        outcome.generated_sql
        .sql
        .upper()
    )

    assert (
        "SUM(LOAN_BAL_RMB)"
        in sql
    )

    assert (
        "TECH_LOAN_BALANCE"
        in sql
    )

    assert (
        "DT = '202607'"
        in sql
    )

    assert (
        "IS_HIGH_TECH_MFG_LOAN_CODE"
        in sql
    )

    assert (
        outcome.evidence
        is not None
    )


def test_multiple_simple_metrics_compile():

    compiler = MetricSQLCompiler(
        semantic_model=(
            _semantic_model(
                _balance_metric(),
                _count_metric(),
            )
        )
    )

    outcome = compiler.compile(
        plan=QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),

            dimensions=(),

            metrics=(
                "tech_loan_balance",
                "enterprise_count",
            ),
        ),

        linked_schema=(
            _linked_schema()
        ),

        dialect="maxcompute",
    )

    assert (
        outcome.status
        is CompilationStatus.COMPILED
    )

    sql = (
        outcome
        .generated_sql
        .sql
        .upper()
    )

    assert (
        "COUNT(DISTINCT"
        in sql
    )


def test_dimension_query_compiles_group_by():

    compiler = MetricSQLCompiler(
        semantic_model=(
            _semantic_model(
                _balance_metric()
            )
        )
    )

    outcome = compiler.compile(
        plan=QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),

            dimensions=(
                "region_code",
            ),

            metrics=(
                "tech_loan_balance",
            ),

            group_by=(
                "region_code",
            ),
        ),

        linked_schema=(
            _linked_schema(
                include_region=True
            )
        ),

        dialect="maxcompute",
    )

    assert (
        outcome.status
        is CompilationStatus.COMPILED
    )

    sql = (
        outcome
        .generated_sql
        .sql
        .upper()
    )

    assert (
        "GROUP BY REGION_CODE"
        in sql
    )


def test_complex_metric_falls_back():

    compiler = MetricSQLCompiler(
        semantic_model=(
            _semantic_model(
                _complex_metric()
            )
        )
    )

    schema = LinkedSchema(
        tables=(
            LinkedTable(
                metadata=_table()
            ),
        ),

        bindings=(
            SchemaBinding(
                kind=(
                    SchemaBindingKind.TABLE
                ),

                logical_name=(
                    "ods_hd_100_cldkxx"
                ),

                physical_table=(
                    TABLE_NAME
                ),
            ),

            SchemaBinding(
                kind=(
                    SchemaBindingKind.METRIC
                ),

                logical_name=(
                    "weighted_rate"
                ),

                physical_table=(
                    TABLE_NAME
                ),

                physical_columns=(
                    "loan_bal_rmb",
                ),
            ),
        ),
    )

    outcome = compiler.compile(
        plan=QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),

            dimensions=(),

            metrics=(
                "weighted_rate",
            ),
        ),

        linked_schema=schema,

        dialect="maxcompute",
    )

    assert (
        outcome.status
        is (
            CompilationStatus
            .NOT_COMPILABLE
        )
    )

    assert (
        outcome.fallback_reason
        is (
            CompilationFallbackReason
            .COMPLEX_EXPRESSION
        )
    )


def test_or_filter_falls_back_to_llm():

    compiler = MetricSQLCompiler(
        semantic_model=(
            _semantic_model(
                _balance_metric()
            )
        )
    )

    outcome = compiler.compile(
        plan=QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),

            dimensions=(),

            metrics=(
                "tech_loan_balance",
            ),

            filters=(
                (
                    "dt = '202607' "
                    "OR dt = '202608'"
                ),
            ),
        ),

        linked_schema=(
            _linked_schema()
        ),

        dialect="maxcompute",
    )

    assert (
        outcome.status
        is (
            CompilationStatus
            .NOT_COMPILABLE
        )
    )

    assert (
        outcome.fallback_reason
        is (
            CompilationFallbackReason
            .UNSUPPORTED_FILTER
        )
    )


def test_dimension_without_group_by_falls_back():

    compiler = MetricSQLCompiler(
        semantic_model=(
            _semantic_model(
                _balance_metric()
            )
        )
    )

    outcome = compiler.compile(
        plan=QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),

            dimensions=(
                "region_code",
            ),

            metrics=(
                "tech_loan_balance",
            ),

            group_by=(),
        ),

        linked_schema=(
            _linked_schema(
                include_region=True
            )
        ),

        dialect="maxcompute",
    )

    assert (
        outcome.status
        is (
            CompilationStatus
            .NOT_COMPILABLE
        )
    )

    assert (
        outcome.fallback_reason
        is (
            CompilationFallbackReason
            .INVALID_GROUPING
        )
    )