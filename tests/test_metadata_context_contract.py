from __future__ import annotations

from sql_pilot_engine.analysis.facts import (
    SQLFacts,
)
from sql_pilot_engine.llm.context_builder import (
    build_metadata_context_text,
)
from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableLookupResult,
    TableMetadata,
)


class FakeMetadataProvider:

    def __init__(
        self,
        table: TableMetadata,
    ) -> None:
        self.table = table

    def get_table(
        self,
        full_name: str,
    ) -> TableLookupResult:
        _ = full_name

        return (
            TableLookupResult
            .found(
                self.table
            )
        )


def build_facts() -> SQLFacts:

    return SQLFacts(
        statement_count=1,
        statement_types=(
            "select",
        ),
        source_tables=(
            "ods_test_table",
        ),
        target_tables=(),
        insert_target_table=None,
        referenced_tables=(
            "ods_test_table",
        ),
        cte_names=(),
        table_references=(),
        column_references=(),
        select_aliases=(),
        has_select_star=False,
        has_drop=False,
        has_truncate=False,
        has_write_operation=False,
        has_partition_clause=False,
    )


def test_missing_partition_fact_is_not_rendered_as_false():

    table = TableMetadata(
        full_name="ods_test_table",
        description="测试表",
        columns={
            "dt": ColumnMetadata(
                name="dt",
                data_type="",
                description=(
                    "数据报送日期分区字段"
                ),
            ),
        },
        partition_fields=(),
    )

    provider = FakeMetadataProvider(
        table
    )

    text = build_metadata_context_text(
        facts=build_facts(),
        metadata_provider=provider,
    )

    assert (
        "Is Partitioned: False"
        not in text
    )

    assert (
        "Partition Fields: None"
        not in text
    )

    assert (
        "Is Partitioned:"
        not in text
    )

    assert (
        "Partition Fields:"
        not in text
    )


def test_declared_partition_fields_are_rendered():

    table = TableMetadata(
        full_name="ods_test_table",
        description="测试表",
        columns={
            "dt": ColumnMetadata(
                name="dt",
                data_type="STRING",
                description=(
                    "数据报送日期分区字段"
                ),
            ),
        },
        partition_fields=(
            "dt",
        ),
    )

    provider = FakeMetadataProvider(
        table
    )

    text = build_metadata_context_text(
        facts=build_facts(),
        metadata_provider=provider,
    )

    assert (
        "Is Partitioned: True"
        in text
    )

    assert (
        "Partition Fields: dt"
        in text
    )