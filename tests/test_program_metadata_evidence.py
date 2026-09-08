from sql_pilot_engine.evidence.program_metadata import (
    ColumnResolutionStatus,
    MetadataObjectRole,
    ProgramMetadataResolver,
)
from sql_pilot_engine.metadata.mock_provider import (
    MockMetadataProvider,
)
from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    MetadataLookupStatus,
    TableMetadata,
)
from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)


def _provider():
    return MockMetadataProvider(
        tables=(
            TableMetadata(
                full_name=(
                    "ods.loan_detail"
                ),
                columns={
                    "id": ColumnMetadata(
                        name="id",
                        data_type="bigint",
                    ),
                    "amount": ColumnMetadata(
                        name="amount",
                        data_type="decimal(18,2)",
                    ),
                    "dt": ColumnMetadata(
                        name="dt",
                        data_type="string",
                    ),
                },
                partition_fields=(
                    "dt",
                ),
            ),
            TableMetadata(
                full_name=(
                    "dws.loan_summary"
                ),
                columns={
                    "id": ColumnMetadata(
                        name="id",
                        data_type="bigint",
                    ),
                    "amount": ColumnMetadata(
                        name="amount",
                        data_type="decimal(18,2)",
                    ),
                    "dt": ColumnMetadata(
                        name="dt",
                        data_type="string",
                    ),
                },
                partition_fields=(
                    "dt",
                ),
            ),
        )
    )


def _resolve(
    sql: str,
):
    analysis = (
        ProgramAnalysisService()
        .analyze(sql)
    )

    assert analysis.program is not None

    return (
        ProgramMetadataResolver(
            _provider()
        )
        .resolve(
            analysis.program
        )
    )


def test_physical_read_table_resolves():
    evidence = _resolve(
        """
        SELECT id
        FROM ods.loan_detail
        """
    )

    table = next(
        item
        for item
        in evidence.tables
        if (
            item.role
            is MetadataObjectRole.READ_SOURCE
        )
    )

    assert (
        table.status
        is MetadataLookupStatus.FOUND
    )

    assert (
        table.requested_table
        == "ods.loan_detail"
    )


def test_write_target_is_resolved_separately():
    evidence = _resolve(
        """
        INSERT OVERWRITE TABLE
            dws.loan_summary
        PARTITION(dt='202609')
        SELECT
            id,
            amount
        FROM ods.loan_detail
        """
    )

    roles = {
        (
            item.role,
            item.requested_table,
            item.status,
        )
        for item
        in evidence.tables
    }

    assert (
        MetadataObjectRole.READ_SOURCE,
        "ods.loan_detail",
        MetadataLookupStatus.FOUND,
    ) in roles

    assert (
        MetadataObjectRole.WRITE_TARGET,
        "dws.loan_summary",
        MetadataLookupStatus.FOUND,
    ) in roles


def test_qualified_column_resolves_by_alias():
    evidence = _resolve(
        """
        SELECT l.amount
        FROM ods.loan_detail l
        """
    )

    column = next(
        item
        for item
        in evidence.columns
        if item.column.name == "amount"
    )

    assert (
        column.status
        is ColumnResolutionStatus.RESOLVED
    )

    assert (
        column.source_alias
        == "l"
    )

    assert (
        column.physical_table
        == "ods.loan_detail"
    )

    assert (
        column.metadata
        is not None
    )

    assert (
        column.metadata.data_type
        == "decimal(18,2)"
    )


def test_single_source_unqualified_column_resolves():
    evidence = _resolve(
        """
        SELECT amount
        FROM ods.loan_detail
        """
    )

    column = next(
        item
        for item
        in evidence.columns
        if item.column.name == "amount"
    )

    assert (
        column.status
        is ColumnResolutionStatus.RESOLVED
    )


def test_absent_column_is_authoritative_absent():
    evidence = _resolve(
        """
        SELECT fake_column
        FROM ods.loan_detail
        """
    )

    column = next(
        item
        for item
        in evidence.columns
        if (
            item.column.name
            == "fake_column"
        )
    )

    assert (
        column.status
        is ColumnResolutionStatus.ABSENT
    )


def test_multiple_sources_without_qualifier_does_not_guess():
    evidence = _resolve(
        """
        SELECT id
        FROM ods.loan_detail a
        JOIN dws.loan_summary b
          ON a.id = b.id
        """
    )

    column = next(
        item
        for item
        in evidence.columns
        if (
            item.column.name == "id"
            and item.column.qualifier
            is None
        )
    )

    assert (
        column.status
        is (
            ColumnResolutionStatus
            .UNRESOLVED_SOURCE
        )
    )


def test_cte_source_is_not_queried_as_physical_metadata():
    evidence = _resolve(
        """
        WITH base AS (
            SELECT
                id,
                amount
            FROM ods.loan_detail
        )
        SELECT b.amount
        FROM base b
        """
    )

    column = next(
        item
        for item
        in evidence.columns
        if (
            item.column.name == "amount"
            and item.source_scope_id
            is not None
        )
    )

    assert (
        column.status
        is (
            ColumnResolutionStatus
            .NON_PHYSICAL_SOURCE
        )
    )


def test_select_alias_is_not_validated_as_physical_column():
    evidence = _resolve(
        """
        SELECT
            SUM(amount) AS total_amount
        FROM ods.loan_detail
        ORDER BY total_amount
        """
    )

    alias_ref = next(
        item
        for item
        in evidence.columns
        if (
            item.column.name
            == "total_amount"
        )
    )

    assert (
        alias_ref.status
        is ColumnResolutionStatus.SELECT_ALIAS
    )