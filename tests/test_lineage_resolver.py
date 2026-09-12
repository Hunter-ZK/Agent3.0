from __future__ import annotations

from dataclasses import replace

import pytest

from metadata_test_factory import (
    make_column_metadata,
    make_table_metadata,
)

from sql_pilot_engine.evidence.lineage import (
    DerivedLineageStatus,
    LineageDiffKind,
    LineageEvidenceError,
)

from sql_pilot_engine.evidence.lineage_resolver import (
    LineageEvidenceResolver,
)

from sql_pilot_engine.evidence.program_metadata import (
    ProgramMetadataResolver,
)

from sql_pilot_engine.metadata.catalog import (
    ColumnSearchResult,
    TableSearchResult,
)

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    PhysicalColumnRef,
    TableLookupResult,
    TableMetadata,
)

from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)


# ============================================================
# Test Metadata Repository
# ============================================================


class _InMemoryMetadataRepository:
    """
    测试专用 MetadataProvider + MetadataCatalog。

    这里不测试 SQLite。

    SQLite Repository 已经有自己的测试。

    Lineage Resolver 测试只关心：

        给定确定的 Metadata，
        Resolver 能否正确组合能力。
    """

    def __init__(
        self,
        tables: tuple[
            TableMetadata,
            ...,
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

        normalized = (
            full_name
            .strip()
            .lower()
        )

        table = (
            self._tables.get(
                normalized
            )
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

        results: list[
            TableSearchResult
        ] = []

        for table in (
            self._tables.values()
        ):

            if (
                table
                .technical
                .table_name
                != normalized
            ):
                continue

            results.append(
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
            )

        return tuple(
            sorted(
                results,
                key=lambda item:
                    item.full_name,
            )
        )

    # 下面三个方法只是满足完整 Catalog Contract。
    #
    # 本组测试不会调用。

    def find_tables(
        self,
        keyword: str,
        *,
        limit: int = 20,
    ) -> tuple[
        TableSearchResult,
        ...,
    ]:
        _ = keyword
        _ = limit
        return ()

    def find_columns(
        self,
        keyword: str,
        *,
        limit: int = 50,
    ) -> tuple[
        ColumnSearchResult,
        ...,
    ]:
        _ = keyword
        _ = limit
        return ()

    def find_column_usages(
        self,
        column_name: str,
    ) -> tuple[
        ColumnSearchResult,
        ...,
    ]:
        _ = column_name
        return ()


# ============================================================
# Metadata Builders
# ============================================================


def _ref(
    table: str,
    column: str,
) -> PhysicalColumnRef:

    return PhysicalColumnRef(
        table_full_name=table,
        column_name=column,
    )


def _column(
    name: str,
    *,
    data_type: str = "string",
    ordinal_position: int = 1,
    declared: tuple[
        PhysicalColumnRef,
        ...,
    ] = (),
) -> ColumnMetadata:
    """
    在现有 metadata_test_factory 基础上，
    仅补充本测试需要的 declared lineage。

    不要求你再修改公共 test factory。
    """

    column = (
        make_column_metadata(
            name=name,
            data_type=data_type,
            ordinal_position=(
                ordinal_position
            ),
        )
    )

    if not declared:
        return column

    return replace(
        column,

        technical=replace(
            column.technical,

            declared_upstream_columns=(
                declared
            ),
        ),

        management=replace(
            column.management,

            lineage_confirmation_status=(
                "confirmed"
            ),
        ),
    )


def _table(
    full_name: str,
    columns: tuple[
        ColumnMetadata,
        ...,
    ],
    *,
    partition_fields: tuple[
        str,
        ...,
    ] = (),
) -> TableMetadata:

    return make_table_metadata(
        full_name=full_name,

        columns={
            column.name:
                column

            for column
            in columns
        },

        partition_fields=(
            partition_fields
        ),
    )


# ============================================================
# Full Resolution Helper
# ============================================================


def _resolve(
    sql: str,
    *tables: TableMetadata,
):
    """
    真正跑：

        Program Analysis
            ↓
        Program Metadata Evidence
            ↓
        Lineage Evidence

    所以这是集成测试，
    不是单函数测试。
    """

    analysis = (
        ProgramAnalysisService()
        .analyze(
            sql,
            dialect="maxcompute",
        )
    )

    assert (
        analysis.program
        is not None
    ), analysis.failure_reason

    repository = (
        _InMemoryMetadataRepository(
            tuple(tables)
        )
    )

    metadata_evidence = (
        ProgramMetadataResolver(
            provider=repository,
            catalog=repository,
        )
        .resolve(
            analysis.program
        )
    )

    lineage_evidence = (
        LineageEvidenceResolver()
        .resolve(
            analysis.program,
            metadata_evidence,
            dialect="maxcompute",
        )
    )

    return lineage_evidence


def _target_column(
    lineage,
    column_name: str,
):

    return next(
        item

        for item
        in lineage.columns

        if (
            item
            .target
            .column_name
            == column_name
        )
    )


# ============================================================
# Gate 1
#
# Direct physical field
# +
# Declared = Derived
# ============================================================


def test_direct_insert_builds_matching_lineage():

    source = _table(
        "project_src.loan_detail",

        (
            _column(
                "customer_id",
                ordinal_position=1,
            ),

            _column(
                "amount",
                data_type="bigint",
                ordinal_position=2,
            ),
        ),
    )

    target = _table(
        "project_dwd.loan_result",

        (
            _column(
                "customer_id",

                ordinal_position=1,

                declared=(
                    _ref(
                        "project_src.loan_detail",
                        "customer_id",
                    ),
                ),
            ),

            _column(
                "amount",

                data_type="bigint",

                ordinal_position=2,

                declared=(
                    _ref(
                        "project_src.loan_detail",
                        "amount",
                    ),
                ),
            ),
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT
            customer_id,
            amount

        FROM project_src.loan_detail
        """,

        source,
        target,
    )

    amount = _target_column(
        lineage,
        "amount",
    )

    assert (
        amount.target
        == _ref(
            "project_dwd.loan_result",
            "amount",
        )
    )

    assert (
        amount.derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "amount",
            ),
        )
    )

    assert (
        amount.declared_upstream
        == amount.derived_upstream
    )

    assert (
        amount.diff.kind
        is LineageDiffKind.MATCH
    )


# ============================================================
# Gate 2
#
# SQL 使用 bare table。
#
# Metadata Resolver：
#
#     loan_detail
#       ↓
#     project_src.loan_detail
#
# 最终 Lineage 必须输出 canonical identity。
# ============================================================


def test_bare_source_is_canonicalized_in_final_lineage():

    source = _table(
        "project_src.loan_detail",

        (
            _column(
                "amount",
                data_type="bigint",
            ),
        ),
    )

    target = _table(
        "project_dwd.loan_result",

        (
            _column(
                "amount",
                data_type="bigint",
            ),
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        SELECT amount

        FROM loan_detail
        """,

        source,
        target,
    )

    amount = _target_column(
        lineage,
        "amount",
    )

    assert (
        amount.derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "amount",
            ),
        )
    )


# ============================================================
# Gate 3
#
# Static Partition
#
# dt = '202609'
# 不来自 SELECT projection。
# ============================================================


def test_static_partition_does_not_consume_projection():

    source = _table(
        "project_src.loan_detail",

        (
            _column(
                "customer_id",
                ordinal_position=1,
            ),
        ),
    )

    target = _table(
        "project_dwd.loan_result",

        (
            _column(
                "customer_id",
                ordinal_position=1,
            ),

            _column(
                "dt",
                ordinal_position=2,
            ),
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

    customer_id = (
        _target_column(
            lineage,
            "customer_id",
        )
    )

    dt = _target_column(
        lineage,
        "dt",
    )

    assert (
        customer_id.projection_index
        == 0
    )

    assert (
        dt.projection_index
        is None
    )

    assert (
        dt.derived_upstream
        == ()
    )

    assert (
        dt.derived_status
        is
        DerivedLineageStatus
        .NO_PHYSICAL_UPSTREAM
    )


# ============================================================
# Gate 4
#
# Dynamic Partition
#
# PARTITION(dt)
#
# dt 必须来自 SELECT 最后一个 projection。
# ============================================================


def test_dynamic_partition_consumes_projection():

    source = _table(
        "project_src.loan_detail",

        (
            _column(
                "customer_id",
                ordinal_position=1,
            ),

            _column(
                "dt",
                ordinal_position=2,
            ),
        ),
    )

    target = _table(
        "project_dwd.loan_result",

        (
            _column(
                "customer_id",
                ordinal_position=1,
            ),

            _column(
                "dt",
                ordinal_position=2,
            ),
        ),

        partition_fields=(
            "dt",
        ),
    )

    lineage = _resolve(
        """
        INSERT OVERWRITE TABLE
            project_dwd.loan_result

        PARTITION(dt)

        SELECT
            customer_id,
            dt

        FROM project_src.loan_detail
        """,

        source,
        target,
    )

    dt = _target_column(
        lineage,
        "dt",
    )

    assert (
        dt.projection_index
        == 1
    )

    assert (
        dt.derived_upstream
        == (
            _ref(
                "project_src.loan_detail",
                "dt",
            ),
        )
    )


# ============================================================
# Gate 5
#
# Metadata Declared
#     amount
#
# SQL Derived
#     rate
#
# 必须保留双方，不自动决定谁对。
# ============================================================


def test_declared_and_derived_mismatch_is_preserved():

    source = _table(
        "project_src.loan_detail",

        (
            _column(
                "amount",
                data_type="bigint",
                ordinal_position=1,
            ),

            _column(
                "rate",
                data_type="double",
                ordinal_position=2,
            ),
        ),
    )

    target = _table(
        "project_dwd.loan_result",

        (
            _column(
                "total_amount",

                data_type="double",

                declared=(
                    _ref(
                        "project_src.loan_detail",
                        "amount",
                    ),
                ),
            ),
        ),
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

    result = _target_column(
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


# ============================================================
# Gate 6
#
# 正式 Lineage 不允许 source Metadata 缺失后继续猜。
# ============================================================


def test_missing_source_metadata_blocks_lineage():

    target = _table(
        "project_dwd.loan_result",

        (
            _column(
                "amount",
                data_type="bigint",
            ),
        ),
    )

    with pytest.raises(
        LineageEvidenceError,
        match=(
            "resolved read-source Metadata"
        ),
    ):

        _resolve(
            """
            INSERT OVERWRITE TABLE
                project_dwd.loan_result

            SELECT amount

            FROM project_src.missing_source
            """,

            target,
        )