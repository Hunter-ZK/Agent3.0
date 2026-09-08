from __future__ import annotations

from collections.abc import Iterable

from sql_pilot_engine.evidence.program_metadata import (
    ColumnResolutionStatus,
    MetadataObjectRole,
    ProgramMetadataResolver,
    TableResolutionStatus,
)
from sql_pilot_engine.metadata.catalog import TableSearchResult
from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableLookupResult,
    TableMetadata,
)
from sql_pilot_engine.program.service import ProgramAnalysisService


class _InMemoryMetadataRepository:
    """测试用权威 Metadata：同时实现 exact Provider 与 identifier Catalog。"""

    def __init__(self, tables: Iterable[TableMetadata]) -> None:
        self._tables = {
            table.full_name.lower(): table
            for table in tables
        }

    def get_table(self, full_name: str) -> TableLookupResult:
        table = self._tables.get(full_name.strip().lower())
        if table is None:
            return TableLookupResult.not_found()
        return TableLookupResult.found(table)

    def find_table_identifiers(
        self,
        table_name: str,
    ) -> tuple[TableSearchResult, ...]:
        normalized = table_name.strip().lower()
        matches = [
            table
            for table in self._tables.values()
            if (
                table.full_name == normalized
                or table.full_name.rsplit(".", 1)[-1] == normalized
            )
        ]
        return tuple(
            TableSearchResult(
                full_name=table.full_name,
                description=table.description,
                layer=table.layer,
            )
            for table in sorted(matches, key=lambda item: item.full_name)
        )


def _table(
    full_name: str,
    *,
    columns: tuple[str, ...],
    partition_fields: tuple[str, ...] = (),
) -> TableMetadata:
    return TableMetadata(
        full_name=full_name,
        columns={
            name: ColumnMetadata(name=name, data_type="string")
            for name in columns
        },
        partition_fields=partition_fields,
    )


def _resolve(sql: str, *tables: TableMetadata):
    analysis = ProgramAnalysisService().analyze(sql)
    assert analysis.program is not None

    repository = _InMemoryMetadataRepository(tables)
    return ProgramMetadataResolver(
        provider=repository,
        catalog=repository,
    ).resolve(analysis.program)


def test_unqualified_table_name_resolves_unique_canonical_name():
    evidence = _resolve(
        "SELECT id FROM loan_detail",
        _table("odps_prd_dwd.loan_detail", columns=("id",)),
    )

    table = next(
        item
        for item in evidence.tables
        if item.role is MetadataObjectRole.READ_SOURCE
    )

    assert table.status is TableResolutionStatus.RESOLVED
    assert table.requested_table == "loan_detail"
    assert table.canonical_table == "odps_prd_dwd.loan_detail"


def test_unqualified_table_name_reports_ambiguity():
    evidence = _resolve(
        "SELECT id FROM loan_detail",
        _table("project_a.loan_detail", columns=("id",)),
        _table("project_b.loan_detail", columns=("id",)),
    )

    table = next(
        item
        for item in evidence.tables
        if item.role is MetadataObjectRole.READ_SOURCE
    )

    assert table.status is TableResolutionStatus.AMBIGUOUS
    assert table.candidates == (
        "project_a.loan_detail",
        "project_b.loan_detail",
    )


def test_qualified_table_name_requires_exact_metadata_identity():
    evidence = _resolve(
        "SELECT id FROM project_b.loan_detail",
        _table("project_a.loan_detail", columns=("id",)),
    )

    table = next(
        item
        for item in evidence.tables
        if item.role is MetadataObjectRole.READ_SOURCE
    )

    assert table.status is TableResolutionStatus.ABSENT


def test_unqualified_column_resolves_unique_physical_owner():
    evidence = _resolve(
        """
        SELECT amount
        FROM loan_detail a
        JOIN customer b
          ON a.customer_id = b.customer_id
        """,
        _table(
            "odps_prd_dwd.loan_detail",
            columns=("customer_id", "amount"),
        ),
        _table(
            "odps_prd_dim.customer",
            columns=("customer_id", "name"),
        ),
    )

    column = next(
        item
        for item in evidence.columns
        if item.column.name == "amount"
    )

    assert column.status is ColumnResolutionStatus.RESOLVED
    assert column.source_alias == "a"
    assert column.physical_table == "odps_prd_dwd.loan_detail"


def test_unqualified_column_reports_ambiguous_physical_owners():
    evidence = _resolve(
        """
        SELECT amount
        FROM loan_detail a
        JOIN customer b
          ON a.customer_id = b.customer_id
        """,
        _table(
            "odps_prd_dwd.loan_detail",
            columns=("customer_id", "amount"),
        ),
        _table(
            "odps_prd_dim.customer",
            columns=("customer_id", "amount"),
        ),
    )

    column = next(
        item
        for item in evidence.columns
        if item.column.name == "amount"
        and item.column.qualifier is None
    )

    assert column.status is ColumnResolutionStatus.AMBIGUOUS
    assert column.candidate_tables == (
        "odps_prd_dim.customer",
        "odps_prd_dwd.loan_detail",
    )


def test_qualified_column_uses_alias_then_canonical_metadata():
    evidence = _resolve(
        "SELECT l.amount FROM loan_detail l",
        _table("odps_prd_dwd.loan_detail", columns=("amount",)),
    )

    column = next(
        item
        for item in evidence.columns
        if item.column.name == "amount"
    )

    assert column.status is ColumnResolutionStatus.RESOLVED
    assert column.source_alias == "l"
    assert column.physical_table == "odps_prd_dwd.loan_detail"


def test_absent_column_is_authoritative_absent():
    evidence = _resolve(
        "SELECT fake_column FROM loan_detail",
        _table("odps_prd_dwd.loan_detail", columns=("id",)),
    )

    column = next(
        item
        for item in evidence.columns
        if item.column.name == "fake_column"
    )

    assert column.status is ColumnResolutionStatus.ABSENT


def test_cte_source_stays_non_physical_until_lineage():
    evidence = _resolve(
        """
        WITH base AS (
            SELECT id, amount
            FROM loan_detail
        )
        SELECT b.amount
        FROM base b
        """,
        _table(
            "odps_prd_dwd.loan_detail",
            columns=("id", "amount"),
        ),
    )

    outer_amount = next(
        item
        for item in evidence.columns
        if item.column.name == "amount"
        and item.source_scope_id is not None
    )

    assert outer_amount.status is ColumnResolutionStatus.NON_PHYSICAL_SOURCE


def test_write_target_is_resolved_independently_from_read_source():
    evidence = _resolve(
        """
        INSERT OVERWRITE TABLE loan_summary
        PARTITION(dt='202609')
        SELECT id, amount
        FROM loan_detail
        """,
        _table("odps_prd_dwd.loan_detail", columns=("id", "amount")),
        _table(
            "odps_prd_dws.loan_summary",
            columns=("id", "amount", "dt"),
            partition_fields=("dt",),
        ),
    )

    targets = [
        item
        for item in evidence.tables
        if item.role is MetadataObjectRole.WRITE_TARGET
    ]

    assert len(targets) == 1
    assert targets[0].status is TableResolutionStatus.RESOLVED
    assert targets[0].canonical_table == "odps_prd_dws.loan_summary"
