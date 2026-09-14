from __future__ import annotations

from sql_pilot_engine.evidence.program_context import (
    ProgramEvidenceContextBuilder,
)
from sql_pilot_engine.metadata.models import TableLookupResult


SQL = """
SET odps.sql.type.system.odps2 = true;

WITH base AS (
    SELECT /*+ MAPJOIN(d) */
        a.id
    FROM project_src.fact_table a
    LEFT JOIN project_src.dim_table d
      ON a.id = d.id
)
INSERT OVERWRITE TABLE project_dwd.result_table
PARTITION(dt='202609')
SELECT id
FROM base
;
"""


class _EmptyMetadata:
    def get_table(self, full_name: str) -> TableLookupResult:
        _ = full_name
        return TableLookupResult.not_found()

    def find_table_identifiers(self, table_name: str):
        _ = table_name
        return ()

    def find_tables(self, keyword: str, *, limit: int = 20):
        _ = keyword
        _ = limit
        return ()

    def find_columns(self, keyword: str, *, limit: int = 50):
        _ = keyword
        _ = limit
        return ()

    def find_column_usages(self, column_name: str):
        _ = column_name
        return ()


class _ProviderOnly:
    def get_table(self, full_name: str) -> TableLookupResult:
        _ = full_name
        return TableLookupResult.not_found()


def test_program_context_builds_deterministic_structure_without_metadata():
    context = ProgramEvidenceContextBuilder().build(SQL)

    payload = context.to_prompt_payload()

    assert context.statement_count == 1
    assert context.cte_count == 1
    assert context.scope_count >= 2

    assert payload["program"]["read_tables"] == [
        "project_src.dim_table",
        "project_src.fact_table",
    ]

    assert payload["program"]["write_targets"][0]["table"] == (
        "project_dwd.result_table"
    )
    assert payload["program"]["write_targets"][0]["partitions"] == [
        {
            "name": "dt",
            "value": "202609",
            "dynamic": False,
        }
    ]

    assert [item.name for item in context.hints] == ["MAPJOIN"]
    assert context.metadata is None
    assert context.lineage is None


def test_program_context_degrades_lineage_when_authoritative_metadata_is_absent():
    context = ProgramEvidenceContextBuilder().build(
        SQL,
        metadata_provider=_EmptyMetadata(),
    )

    assert context.metadata is not None
    assert context.lineage is None
    assert any(
        item.code == "lineage_unavailable"
        for item in context.diagnostics
    )


def test_program_context_does_not_guess_catalog_from_provider_only():
    context = ProgramEvidenceContextBuilder().build(
        SQL,
        metadata_provider=_ProviderOnly(),
    )

    assert context.metadata is None
    assert context.lineage is None
    assert any(
        item.code == "metadata_catalog_unavailable"
        for item in context.diagnostics
    )
