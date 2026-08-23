from types import (
    SimpleNamespace,
)

from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
)
from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)
from sql_pilot_engine.optimization.context import (
    OptimizationContext,
)
from sql_pilot_engine.optimization.models import (
    RewriteSafety,
)
from sql_pilot_engine.optimization.rules import (
    build_default_optimization_registry,
)


class FakeMetadataProvider:

    def __init__(
        self,
        *,
        is_partitioned: bool,
        partition_fields=(),
    ) -> None:
        self._table = (
            SimpleNamespace(
                is_partitioned=(
                    is_partitioned
                ),
                partition_fields=tuple(
                    partition_fields
                ),
            )
        )

    def get_table(
        self,
        full_name: str,
    ):
        _ = full_name

        return SimpleNamespace(
            status=(
                MetadataLookupStatus.FOUND
            ),
            table=self._table,
            error_message=None,
        )


def analyze(
    sql: str,
):
    return (
        SQLAnalysisAdapter()
        .analyze(
            sql=sql,
            dialect="maxcompute",
        )
        .facts
    )


def finding_ids(
    *,
    sql: str,
    metadata_provider=None,
):
    facts = analyze(
        sql
    )

    registry = (
        build_default_optimization_registry()
    )

    findings = registry.analyze(
        sql=sql,
        facts=facts,
        context=(
            OptimizationContext(
                metadata_provider=(
                    metadata_provider
                )
            )
        ),
    )

    return {
        finding.rule_id: finding
        for finding in findings
    }


def test_select_star_creates_suggestion():

    sql = """
    SELECT *
    FROM user_table
    """

    findings = finding_ids(
        sql=sql
    )

    finding = findings[
        "SELECT_STAR"
    ]

    assert (
        finding.rewrite_safety
        == RewriteSafety.SUGGESTION_ONLY
    )


def test_distinct_group_by_is_safe_rewrite_candidate():

    sql = """
    SELECT DISTINCT
        industry_code,
        SUM(loan_bal_rmb)
    FROM loan_table
    GROUP BY industry_code
    """

    findings = finding_ids(
        sql=sql
    )

    finding = findings[
        "REDUNDANT_DISTINCT_WITH_GROUP_BY"
    ]

    assert (
        finding.rewrite_safety
        == RewriteSafety.SAFE_REWRITE
    )


def test_partition_table_without_filter_creates_finding():

    sql = """
    SELECT
        SUM(loan_bal_rmb)
    FROM ods_hd_100_cldkxx
    """

    provider = (
        FakeMetadataProvider(
            is_partitioned=True,
            partition_fields=(
                "dt",
            ),
        )
    )

    findings = finding_ids(
        sql=sql,
        metadata_provider=provider,
    )

    assert (
        "MISSING_PARTITION_FILTER"
        in findings
    )


def test_partition_filter_prevents_finding():

    sql = """
    SELECT
        SUM(loan_bal_rmb)
    FROM ods_hd_100_cldkxx
    WHERE
        dt = '202607'
    """

    provider = (
        FakeMetadataProvider(
            is_partitioned=True,
            partition_fields=(
                "dt",
            ),
        )
    )

    findings = finding_ids(
        sql=sql,
        metadata_provider=provider,
    )

    assert (
        "MISSING_PARTITION_FILTER"
        not in findings
    )


def test_non_partition_table_has_no_partition_finding():

    sql = """
    SELECT
        SUM(loan_bal_rmb)
    FROM ods_hd_100_cldkxx
    """

    provider = (
        FakeMetadataProvider(
            is_partitioned=False,
        )
    )

    findings = finding_ids(
        sql=sql,
        metadata_provider=provider,
    )

    assert (
        "MISSING_PARTITION_FILTER"
        not in findings
    )


def test_multi_select_skips_safe_distinct_rewrite():

    sql = """
    WITH x AS (
        SELECT DISTINCT
            industry_code
        FROM loan_table
    )
    SELECT
        industry_code,
        COUNT(*) AS cnt
    FROM x
    GROUP BY industry_code
    """

    findings = finding_ids(
        sql=sql
    )

    assert (
        "REDUNDANT_DISTINCT_WITH_GROUP_BY"
        not in findings
    )