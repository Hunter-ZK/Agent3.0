from __future__ import annotations

from metadata_test_factory import make_column_metadata, make_table_metadata

from sql_pilot_engine.analysis.sql_analysis import SQLAnalysisAdapter
from sql_pilot_engine.context.semantic.models import (
    SemanticFilter,
    SemanticMetric,
    SemanticModel,
)
from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import IssueAction
from sql_pilot_engine.core.trust_evidence import SQLTrustEvidence
from sql_pilot_engine.generation.models import QueryPlan
from sql_pilot_engine.linking.models import LinkedSchema, LinkedTable
from sql_pilot_engine.metadata.models import TableMetadata
from sql_pilot_engine.rules.registry import RuleRegistry


def _physical_table(
    name: str = "odps_prd_dwd.ods_hd_100_cldkxx",
    *,
    partition_fields: tuple[str, ...] = (),
) -> TableMetadata:
    """Build valid nested Metadata for semantic-rule tests.

    The old tests used ``columns={}`` even when declaring ``dt`` as a partition.
    That became an invalid fixture once TableMetadata started enforcing that every
    partition field must exist physically. The release tests intentionally keep the
    production invariant and construct a real minimal schema instead.
    """

    columns = {
        "loan_bal_rmb": make_column_metadata(
            "loan_bal_rmb",
            data_type="decimal(22,2)",
            ordinal_position=1,
        ),
        "ent_code": make_column_metadata(
            "ent_code",
            ordinal_position=2,
        ),
        "is_high_tech_mfg_loan_code": make_column_metadata(
            "is_high_tech_mfg_loan_code",
            ordinal_position=3,
        ),
        "dt": make_column_metadata(
            "dt",
            ordinal_position=4,
        ),
    }

    return make_table_metadata(
        full_name=name,
        columns=columns,
        partition_fields=partition_fields,
    )


def _simple_metric(
    *,
    name: str = "tech_loan_balance",
    table: str = "ods_hd_100_cldkxx",
    aggregation: str | None = "sum",
    source_column: str | None = "loan_bal_rmb",
    fixed_filters: tuple[SemanticFilter, ...] = (),
) -> SemanticMetric:
    expression = (
        "SUM(loan_bal_rmb)"
        if aggregation == "sum"
        else "COUNT(DISTINCT ent_code)"
        if aggregation == "count_distinct"
        else "SUM(loan_bal_rmb * rate) / SUM(loan_bal_rmb)"
    )

    return SemanticMetric(
        name=name,
        description="test metric",
        expression=expression,
        table=table,
        aggregation=aggregation,
        source_column=source_column,
        fixed_filters=fixed_filters,
    )


def _run_rules(
    *,
    sql: str,
    metrics: tuple[SemanticMetric, ...] = (),
    plan_metric_names: tuple[str, ...] | None = None,
    linked_tables: tuple[TableMetadata, ...] = (),
    packs: tuple[str, ...] = ("text_to_sql",),
):
    if plan_metric_names is None:
        plan_metric_names = tuple(metric.name for metric in metrics)

    plan = QueryPlan(
        tables=tuple(table.full_name for table in linked_tables),
        dimensions=(),
        metrics=plan_metric_names,
    )

    evidence = SQLTrustEvidence(
        query_plan=plan,
        linked_schema=LinkedSchema(
            tables=tuple(
                LinkedTable(metadata=table)
                for table in linked_tables
            ),
        ),
        semantic_model=SemanticModel(
            tables=(),
            metrics=metrics,
        ),
    )

    analysis = SQLAnalysisAdapter().analyze(
        sql=sql,
        dialect="maxcompute",
    )
    assert analysis.facts is not None

    context = ReviewContext(
        mode="prod",
        dialect="maxcompute",
        parse_result=analysis.parse_result,
        sql_facts=analysis.facts,
        trust_evidence=evidence,
        rule_packs=packs,
    )

    return RuleRegistry().run(
        sql=sql,
        context=context,
    )


def _issues_by_rule(issues, rule_id: str):
    return [issue for issue in issues if issue.rule_id == rule_id]


def test_metric_table_accepts_approved_source_table() -> None:
    issues = _run_rules(
        sql="SELECT SUM(loan_bal_rmb) FROM ods_hd_100_cldkxx",
        metrics=(_simple_metric(),),
        linked_tables=(_physical_table(),),
    )
    assert _issues_by_rule(issues, "METRIC_TABLE") == []


def test_metric_table_reports_wrong_source_as_advisory() -> None:
    issues = _run_rules(
        sql="SELECT SUM(loan_bal_rmb) FROM another_table",
        metrics=(_simple_metric(),),
        linked_tables=(_physical_table(),),
    )
    metric_issues = _issues_by_rule(issues, "METRIC_TABLE")
    assert len(metric_issues) == 1
    assert metric_issues[0].action is IssueAction.ADVISORY


def test_metric_aggregation_accepts_sum_on_source_column() -> None:
    issues = _run_rules(
        sql="SELECT SUM(loan_bal_rmb) FROM ods_hd_100_cldkxx",
        metrics=(_simple_metric(),),
        linked_tables=(_physical_table(),),
    )
    assert _issues_by_rule(issues, "METRIC_AGGREGATION") == []


def test_metric_aggregation_reports_wrong_function_as_advisory() -> None:
    issues = _run_rules(
        sql="SELECT AVG(loan_bal_rmb) FROM ods_hd_100_cldkxx",
        metrics=(_simple_metric(),),
        linked_tables=(_physical_table(),),
    )
    metric_issues = _issues_by_rule(issues, "METRIC_AGGREGATION")
    assert len(metric_issues) == 1
    assert metric_issues[0].action is IssueAction.ADVISORY


def test_count_distinct_metric_is_supported() -> None:
    metric = _simple_metric(
        name="enterprise_count",
        aggregation="count_distinct",
        source_column="ent_code",
    )
    issues = _run_rules(
        sql="SELECT COUNT(DISTINCT ent_code) FROM ods_hd_100_cldkxx",
        metrics=(metric,),
        linked_tables=(_physical_table(),),
    )
    assert _issues_by_rule(issues, "METRIC_AGGREGATION") == []


def test_expression_only_metric_is_not_forced_into_simple_aggregation_rule() -> None:
    metric = SemanticMetric(
        name="weighted_rate",
        description="weighted rate",
        expression="SUM(loan_bal_rmb * rate) / SUM(loan_bal_rmb)",
        table="ods_hd_100_cldkxx",
        aggregation=None,
        source_column=None,
    )
    table = make_table_metadata(
        full_name="odps_prd_dwd.ods_hd_100_cldkxx",
        columns={
            "loan_bal_rmb": make_column_metadata("loan_bal_rmb"),
            "rate": make_column_metadata("rate"),
        },
    )
    issues = _run_rules(
        sql=(
            "SELECT SUM(loan_bal_rmb * rate) / SUM(loan_bal_rmb) "
            "FROM ods_hd_100_cldkxx"
        ),
        metrics=(metric,),
        linked_tables=(table,),
    )
    assert _issues_by_rule(issues, "METRIC_AGGREGATION") == []


def test_metric_fixed_filter_accepts_matching_predicate() -> None:
    metric = _simple_metric(
        fixed_filters=(
            SemanticFilter(
                column="is_high_tech_mfg_loan_code",
                operator="=",
                value="1",
            ),
        )
    )
    issues = _run_rules(
        sql=(
            "SELECT SUM(loan_bal_rmb) FROM ods_hd_100_cldkxx "
            "WHERE is_high_tech_mfg_loan_code = '1'"
        ),
        metrics=(metric,),
        linked_tables=(_physical_table(),),
    )
    assert _issues_by_rule(issues, "METRIC_FIXED_FILTER") == []


def test_metric_fixed_filter_reports_missing_predicate_as_advisory() -> None:
    metric = _simple_metric(
        fixed_filters=(
            SemanticFilter(
                column="is_high_tech_mfg_loan_code",
                operator="=",
                value="1",
            ),
        )
    )
    issues = _run_rules(
        sql="SELECT SUM(loan_bal_rmb) FROM ods_hd_100_cldkxx",
        metrics=(metric,),
        linked_tables=(_physical_table(),),
    )
    metric_issues = _issues_by_rule(issues, "METRIC_FIXED_FILTER")
    assert len(metric_issues) == 1
    assert metric_issues[0].action is IssueAction.ADVISORY


def test_partition_rule_accepts_partition_predicate() -> None:
    table = _physical_table(partition_fields=("dt",))
    issues = _run_rules(
        sql="SELECT * FROM ods_hd_100_cldkxx WHERE dt = '202607'",
        linked_tables=(table,),
    )
    assert _issues_by_rule(issues, "PARTITION_CONSTRAINT") == []


def test_partition_rule_reports_missing_constraint_as_advisory() -> None:
    table = _physical_table(partition_fields=("dt",))
    issues = _run_rules(
        sql="SELECT * FROM ods_hd_100_cldkxx",
        linked_tables=(table,),
    )
    partition_issues = _issues_by_rule(issues, "PARTITION_CONSTRAINT")
    assert len(partition_issues) == 1
    assert partition_issues[0].action is IssueAction.ADVISORY


def test_semantic_evidence_rules_are_text_to_sql_only() -> None:
    issues = _run_rules(
        sql="SELECT AVG(loan_bal_rmb) FROM another_table",
        metrics=(_simple_metric(),),
        linked_tables=(_physical_table(),),
        packs=(),
    )
    semantic_rule_ids = {
        "METRIC_TABLE",
        "METRIC_AGGREGATION",
        "METRIC_FIXED_FILTER",
        "PARTITION_CONSTRAINT",
    }
    assert not any(issue.rule_id in semantic_rule_ids for issue in issues)
