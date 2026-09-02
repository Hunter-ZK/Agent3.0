from __future__ import annotations

from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
)

from sql_pilot_engine.core.context import (
    ReviewContext,
)

from sql_pilot_engine.rules.registry import (
    RuleRegistry,
)


def _review_with_packs(
    sql: str,
    *,
    packs: tuple[
        str,
        ...
    ],
):
    analysis = (
        SQLAnalysisAdapter()
        .analyze(
            sql=sql,
            dialect="maxcompute",
        )
    )

    assert analysis.facts is not None

    context = ReviewContext(
        mode="prod",

        dialect="maxcompute",

        parse_result=(
            analysis.parse_result
        ),

        sql_facts=(
            analysis.facts
        ),

        rule_packs=packs,
    )

    return (
        RuleRegistry()
        .run(
            sql=sql,
            context=context,
        )
    )


def test_text_to_sql_blocks_write_operation(
) -> None:

    issues = _review_with_packs(
        """
        INSERT INTO target_table
        SELECT *
        FROM source_table
        """,

        packs=(
            "text_to_sql",
        ),
    )

    assert any(
        issue.rule_id
        == "TEXT_TO_SQL_READ_ONLY"
        for issue
        in issues
    )


def test_base_runtime_does_not_apply_text_to_sql_policy(
) -> None:

    issues = _review_with_packs(
        """
        INSERT INTO target_table
        SELECT *
        FROM source_table
        """,

        packs=(),
    )

    assert not any(
        issue.rule_id
        == "TEXT_TO_SQL_READ_ONLY"
        for issue
        in issues
    )


def test_text_to_sql_allows_select(
) -> None:

    issues = _review_with_packs(
        """
        SELECT *
        FROM source_table
        """,

        packs=(
            "text_to_sql",
        ),
    )

    assert not any(
        issue.rule_id
        == "TEXT_TO_SQL_READ_ONLY"
        for issue
        in issues
    )
    

def test_rule_catalog_only_exposes_active_capability_rules(
) -> None:

    registry = (
        RuleRegistry()
    )

    base_catalog = (
        registry
        .build_catalog_text()
    )

    assert (
        "TEXT_TO_SQL_READ_ONLY"
        not in base_catalog
    )

    text_to_sql_catalog = (
        registry
        .build_catalog_text(
            rule_packs=(
                "text_to_sql",
            )
        )
    )

    assert (
        "TEXT_TO_SQL_READ_ONLY"
        in text_to_sql_catalog
    )