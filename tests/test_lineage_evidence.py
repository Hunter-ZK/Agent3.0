from __future__ import annotations

from collections.abc import Iterable

import pytest

from metadata_test_factory import (
    make_column_metadata,
    make_table_metadata,
)

from sql_pilot_engine.evidence.lineage import (
    DerivedLineageStatus,
    LineageDiffKind,
    LineageEvidenceError,
    LineageEvidenceResolver,
)

from sql_pilot_engine.evidence.program_metadata import (
    ProgramMetadataResolver,
)

from sql_pilot_engine.metadata.catalog import (
    TableSearchResult,
)

from sql_pilot_engine.metadata.models import (
    PhysicalColumnRef,
    TableLookupResult,
    TableMetadata,
)

from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)


class _InMemoryMetadataRepository:
    """
    Lineage 单测使用的：

    MetadataProvider
        +
    MetadataCatalog

    只实现当前测试真正需要的接口。
    """

    def __init__(
        self,
        tables: Iterable[
            TableMetadata
        ],
    ) -> None:

        self._tables = {
            table.full_name:
                table

            for table
            in tables
        }

    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:

        table = self._tables.get(
            full_name
            .strip()
            .lower()
        )

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

    def find_table_identifiers(
        self,
        table_name: str,
    ) -> tuple[
        TableSearchResult,
        ...,
    ]:

        normalized = (
            table_name
            .strip()
            .lower()
        )

        matches = tuple(
            table

            for table
            in self._tables.values()

            if (
                table.full_name
                == normalized

                or (
                    table
                    .technical
                    .table_name
                    == normalized
                )
            )
        )

        return tuple(
            TableSearchResult(
                full_name=(
                    table.full_name
                ),

                description=(
                    table
                    .business
                    .description
                ),
            )

            for table
            in sorted(
                matches,
                key=lambda item:
                    item.full_name,
            )
        )


def _ref(
    table: str,
    column: str,
) -> PhysicalColumnRef:

    return PhysicalColumnRef(
        table_full_name=table,
        column_name=column,
    )


def _table(
    full_name: str,
    columns: tuple[
        str,
        ...,
    ],
    *,
    declared: dict[
        str,
        tuple[
            PhysicalColumnRef,
            ...,
        ],
    ] | None = None,
    partition_fields: tuple[
        str,
        ...,
    ] = (),
) -> TableMetadata:

    declared = (
        declared
        or {}
    )

    return make_table_metadata(
        full_name=full_name,

        columns={
            name: (
                make_column_metadata(
                    name=name,

                    data_type=(
                        "bigint"

                        if name in {
                            "amount",
                            "rate",
                            "total_amount",
                        }

                        else "string"
                    ),

                    declared_upstream_columns=(
                        declared.get(
                            name,
                            (),
                        )
                    ),

                    lineage_confirmation_status=(
                        "confirmed"

                        if name
                        in declared

                        else None
                    ),
                )
            )

            for name
            in columns
        },

        partition_fields=(
            partition_fields
        ),
    )


def _resolve(
    sql: str,
    *tables: TableMetadata,
):

    analysis = (
        ProgramAnalysisService()
        .analyze(
            sql
        )
    )

    assert (
        analysis.program
        is not None
    )

    repository = (
        _InMemoryMetadataRepository(
            tables
        )
    )

    metadata = (
        ProgramMetadataResolver(
            provider=repository,
            catalog=repository,
        )
        .resolve(
            analysis.program
        )
    )

    return (
        LineageEvidenceResolver()
        .resolve(
            analysis.program,
            metadata,
        )
    )


def _column(
    lineage,
    target_name: str,
):

    return next(
        item

        for item
        in lineage.columns

        if (
            item
            .target
            .column_name
            == target_name
        )
    )


def test_direct_column_matches_declared_lineage():

    source = _table(
        "project_src.loan_detail",
        (
            "customer_id",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "customer_id",
        ),

        declared={
            "customer_id": (
                _ref(
                    "project_src.loan_detail",
                    "customer_id",
                ),
            )
        },
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT customer_id

        FROM project_src.loan_detail
        """,
        source,
        target,
    )

    result = _column(
        lineage,
        "customer_id",
    )

    assert (
        result.derived_status
        is DerivedLineageStatus.RESOLVED
    )

    assert (
        result.derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "customer_id",
            ),
        )
    )

    assert (
        result.declared_upstream
        == result.derived_upstream
    )

    assert (
        result.diff.kind
        is LineageDiffKind.MATCH
    )


def test_cte_column_reaches_physical_source():

    source = _table(
        "project_src.loan_detail",
        (
            "amount",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "amount",
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        WITH base AS (
            SELECT amount
            FROM project_src.loan_detail
        )

        SELECT amount
        FROM base
        """,
        source,
        target,
    )

    result = _column(
        lineage,
        "amount",
    )

    assert (
        result.derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "amount",
            ),
        )
    )


def test_derived_expression_keeps_all_inputs():

    source = _table(
        "project_src.loan_detail",
        (
            "amount",
            "rate",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "total_amount",
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT
            amount * rate
                AS total_amount

        FROM project_src.loan_detail
        """,
        source,
        target,
    )

    result = _column(
        lineage,
        "total_amount",
    )

    assert set(
        result.derived_upstream
    ) == {
        _ref(
            "project_src.loan_detail",
            "amount",
        ),

        _ref(
            "project_src.loan_detail",
            "rate",
        ),
    }


def test_select_star_uses_metadata_schema():

    source = _table(
        "project_src.loan_detail",
        (
            "customer_id",
            "amount",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "customer_id",
            "amount",
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT *

        FROM project_src.loan_detail
        """,
        source,
        target,
    )

    assert (
        _column(
            lineage,
            "customer_id",
        )
        .derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "customer_id",
            ),
        )
    )

    assert (
        _column(
            lineage,
            "amount",
        )
        .derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "amount",
            ),
        )
    )


def test_union_collects_both_sources():

    source_a = _table(
        "project_src.loan_a",
        (
            "customer_id",
        ),
    )

    source_b = _table(
        "project_src.loan_b",
        (
            "customer_id",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "customer_id",
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT customer_id
        FROM project_src.loan_a

        UNION ALL

        SELECT customer_id
        FROM project_src.loan_b
        """,
        source_a,
        source_b,
        target,
    )

    result = _column(
        lineage,
        "customer_id",
    )

    assert set(
        result.derived_upstream
    ) == {
        _ref(
            "project_src.loan_a",
            "customer_id",
        ),

        _ref(
            "project_src.loan_b",
            "customer_id",
        ),
    }


def test_aggregation_reaches_source_column():

    source = _table(
        "project_src.loan_detail",
        (
            "amount",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "total_amount",
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT
            SUM(amount)
                AS total_amount

        FROM project_src.loan_detail
        """,
        source,
        target,
    )

    result = _column(
        lineage,
        "total_amount",
    )

    assert (
        result.derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "amount",
            ),
        )
    )


def test_static_partition_has_no_projection_dependency():

    source = _table(
        "project_src.loan_detail",
        (
            "customer_id",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "customer_id",
            "dt",
        ),
        partition_fields=(
            "dt",
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        PARTITION(
            dt='202609'
        )

        SELECT customer_id

        FROM project_src.loan_detail
        """,
        source,
        target,
    )

    partition = _column(
        lineage,
        "dt",
    )

    assert (
        partition.projection_index
        is None
    )

    assert (
        partition.derived_upstream
        == ()
    )

    assert (
        partition.derived_status
        is
        DerivedLineageStatus
        .NO_PHYSICAL_UPSTREAM
    )


def test_join_ambiguity_is_not_guessed():

    source_a = _table(
        "project_src.loan_a",
        (
            "id",
            "join_id",
        ),
    )

    source_b = _table(
        "project_src.loan_b",
        (
            "id",
            "join_id",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "id",
        ),
    )

    with pytest.raises(
        LineageEvidenceError,
        match=(
            "qualification failed"
        ),
    ):

        _resolve(
            """
            INSERT OVERWRITE TABLE
                project_dwd.loan_result

            SELECT id

            FROM project_src.loan_a a

            JOIN project_src.loan_b b
              ON a.join_id = b.join_id
            """,
            source_a,
            source_b,
            target,
        )


def test_declared_only_diff_is_preserved():

    source = _table(
        "project_src.loan_detail",
        (
            "amount",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "flag",
        ),

        declared={
            "flag": (
                _ref(
                    "project_src.loan_detail",
                    "amount",
                ),
            )
        },
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT
            1 AS flag

        FROM project_src.loan_detail
        """,
        source,
        target,
    )

    result = _column(
        lineage,
        "flag",
    )

    assert (
        result.diff.kind
        is
        LineageDiffKind
        .DECLARED_ONLY
    )


def test_path_mismatch_keeps_both_sides():

    source = _table(
        "project_src.loan_detail",
        (
            "amount",
            "rate",
        ),
    )

    target = _table(
        "project_dwd.loan_result",
        (
            "total_amount",
        ),

        declared={
            "total_amount": (
                _ref(
                    "project_src.loan_detail",
                    "amount",
                ),
            )
        },
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT
            rate AS total_amount

        FROM project_src.loan_detail
        """,
        source,
        target,
    )

    result = _column(
        lineage,
        "total_amount",
    )

    assert (
        result.diff.kind
        is
        LineageDiffKind
        .PATH_MISMATCH
    )

    assert (
        result.diff.declared_only
        == (
            _ref(
                "project_src.loan_detail",
                "amount",
            ),
        )
    )

    assert (
        result.diff.derived_only
        == (
            _ref(
                "project_src.loan_detail",
                "rate",
            ),
        )
    )