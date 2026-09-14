from __future__ import annotations

import pytest
from sqlglot import parse_one
from sqlglot.schema import MappingSchema

from sql_pilot_engine.evidence.lineage import (
    DerivedLineageStatus,
    LineageDiffKind,
    LineageEvidenceError,
    SQLGlotDerivedLineageAdapter,
    build_lineage_diff,
)
from sql_pilot_engine.metadata.models import PhysicalColumnRef


def _ref(table: str, column: str) -> PhysicalColumnRef:
    return PhysicalColumnRef(
        table_full_name=table,
        column_name=column,
    )


def _schema(mapping: dict[str, dict[str, str]]) -> MappingSchema:
    return MappingSchema(mapping, dialect="hive")


def _query(sql: str):
    expression = parse_one(sql, dialect="hive")
    assert expression is not None
    return expression


def test_lineage_diff_match() -> None:
    upstream = (_ref("src", "amount"),)

    diff = build_lineage_diff(
        declared=upstream,
        derived=upstream,
        derived_status=DerivedLineageStatus.RESOLVED,
    )

    assert diff.kind is LineageDiffKind.MATCH
    assert diff.declared_only == ()
    assert diff.derived_only == ()


def test_lineage_diff_path_mismatch_preserves_both_sides() -> None:
    declared = (_ref("src", "amount"),)
    derived = (_ref("src", "rate"),)

    diff = build_lineage_diff(
        declared=declared,
        derived=derived,
        derived_status=DerivedLineageStatus.RESOLVED,
    )

    assert diff.kind is LineageDiffKind.PATH_MISMATCH
    assert diff.declared_only == declared
    assert diff.derived_only == derived


@pytest.mark.parametrize(
    "status",
    [
        DerivedLineageStatus.PARTIAL,
        DerivedLineageStatus.UNRESOLVED,
        DerivedLineageStatus.ERROR,
    ],
)
def test_incomplete_derived_lineage_is_not_comparable(
    status: DerivedLineageStatus,
) -> None:
    diff = build_lineage_diff(
        declared=(_ref("src", "amount"),),
        derived=(),
        derived_status=status,
    )

    assert diff.kind is LineageDiffKind.NOT_COMPARABLE


def test_adapter_resolves_direct_physical_column() -> None:
    adapter = SQLGlotDerivedLineageAdapter()

    result = adapter.derive_query(
        _query("SELECT amount FROM source_table"),
        schema=_schema(
            {
                "source_table": {
                    "amount": "BIGINT",
                }
            }
        ),
        dialect="maxcompute",
    )

    assert len(result) == 1
    assert result[0].status is DerivedLineageStatus.RESOLVED
    assert result[0].upstream == (
        _ref("source_table", "amount"),
    )


def test_adapter_traces_cte_and_aggregation_to_physical_leaf() -> None:
    adapter = SQLGlotDerivedLineageAdapter()

    result = adapter.derive_query(
        _query(
            """
            WITH base AS (
                SELECT amount
                FROM source_table
            )
            SELECT SUM(amount) AS total_amount
            FROM base
            """
        ),
        schema=_schema(
            {
                "source_table": {
                    "amount": "BIGINT",
                }
            }
        ),
        dialect="maxcompute",
    )

    assert result[0].status is DerivedLineageStatus.RESOLVED
    assert result[0].upstream == (
        _ref("source_table", "amount"),
    )


def test_adapter_marks_constant_projection_as_no_physical_upstream() -> None:
    adapter = SQLGlotDerivedLineageAdapter()

    result = adapter.derive_query(
        _query("SELECT 1 AS flag"),
        schema=_schema({}),
        dialect="maxcompute",
    )

    assert len(result) == 1
    assert (
        result[0].status
        is DerivedLineageStatus.NO_PHYSICAL_UPSTREAM
    )
    assert result[0].upstream == ()


def test_adapter_supports_unnamed_scalar_subquery_by_projection_index() -> None:
    adapter = SQLGlotDerivedLineageAdapter()

    result = adapter.derive_query(
        _query(
            """
            SELECT (
                SELECT MAX(batch_num)
                FROM submit_org_md
            )
            """
        ),
        schema=_schema(
            {
                "submit_org_md": {
                    "batch_num": "BIGINT",
                }
            }
        ),
        dialect="maxcompute",
    )

    assert len(result) == 1
    assert result[0].projection_index == 0
    assert result[0].status is DerivedLineageStatus.RESOLVED
    assert result[0].upstream == (
        _ref("submit_org_md", "batch_num"),
    )


def test_adapter_fails_closed_when_qualification_is_ambiguous() -> None:
    adapter = SQLGlotDerivedLineageAdapter()

    with pytest.raises(
        LineageEvidenceError,
        match="qualification failed",
    ):
        adapter.derive_query(
            _query(
                """
                SELECT id
                FROM left_table l
                JOIN right_table r
                  ON l.id = r.id
                """
            ),
            schema=_schema(
                {
                    "left_table": {"id": "BIGINT"},
                    "right_table": {"id": "BIGINT"},
                }
            ),
            dialect="maxcompute",
        )
