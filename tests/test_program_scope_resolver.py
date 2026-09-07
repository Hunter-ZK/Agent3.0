from __future__ import annotations

from sql_pilot_engine.analysis.sql_parser import (
    SQLParser,
)
from sql_pilot_engine.program.builder import (
    ProgramBuilder,
)
from sql_pilot_engine.program.preprocessing import (
    preprocess_program_sql,
)
from sql_pilot_engine.program.scope_resolver import (
    ScopeResolver,
)
from sql_pilot_engine.program.enums import (
    SourceBindingKind,
)

def _analyze_scopes(
    raw_sql: str,
):
    preprocess_result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    parse_result = (
        SQLParser().parse(
            preprocess_result.normalized_sql,
            dialect="maxcompute",
        )
    )

    assert (
        parse_result.success
        is True
    ), parse_result.error_message

    program = (
        ProgramBuilder().build(
            preprocess_result=(
                preprocess_result
            ),
            parse_result=parse_result,
        )
    )

    return ScopeResolver().resolve(
        program=program,
        parse_result=parse_result,
    )


def _scope_by_cte(
    program,
    name: str,
):
    return next(
        analysis
        for analysis
        in program.scope_analyses
        if analysis.cte_name == name
    )


def test_each_cte_gets_scope_analysis():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id, amount
            FROM ods.loan_detail
        ),
        summary AS (
            SELECT id, SUM(amount) AS amount
            FROM base
            GROUP BY id
        )
        SELECT *
        FROM summary
        """
    )

    base = _scope_by_cte(
        program,
        "base",
    )

    summary = _scope_by_cte(
        program,
        "summary",
    )

    assert base.cte_name == "base"
    assert summary.cte_name == "summary"


def test_physical_table_is_preserved_in_cte_scope():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id, amount
            FROM odps_prd_ods.ods_loan_detail
        )
        SELECT *
        FROM base
        """
    )

    base = _scope_by_cte(
        program,
        "base",
    )

    assert (
        base.facts.source_tables
        == (
            "odps_prd_ods.ods_loan_detail",
        )
    )


def test_cte_reference_is_not_physical_table():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id, amount
            FROM odps_prd_ods.ods_loan_detail
        ),
        summary AS (
            SELECT id, amount
            FROM base
        )
        SELECT *
        FROM summary
        """
    )

    summary = _scope_by_cte(
        program,
        "summary",
    )

    assert (
        summary.facts.source_tables
        == ()
    )

    assert (
        "base"
        not in summary.facts.referenced_tables
    )


def test_root_scope_does_not_treat_cte_as_physical():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id
            FROM odps_prd_ods.ods_loan_detail
        )
        SELECT *
        FROM base
        """
    )

    root = next(
        analysis
        for analysis
        in program.scope_analyses
        if (
            analysis.scope_id
            == "statement:0:root"
        )
    )

    assert (
        root.facts.source_tables
        == ()
    )


def test_scope_columns_are_local():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT
                id,
                amount
            FROM odps_prd_ods.ods_loan_detail
        ),
        summary AS (
            SELECT
                id,
                SUM(amount) AS total_amount
            FROM base
            GROUP BY id
        )
        SELECT total_amount
        FROM summary
        """
    )

    summary = _scope_by_cte(
        program,
        "summary",
    )

    column_names = {
        item.name
        for item
        in summary.facts.column_references
    }

    assert "id" in column_names
    assert "amount" in column_names

    assert (
        "total_amount"
        in summary.facts.select_aliases
    )


def test_insert_target_is_not_scope_source():
    program = _analyze_scopes(
        """
        INSERT OVERWRITE TABLE dws.loan_summary
        SELECT id
        FROM ods.loan_detail
        """
    )

    root = next(
        analysis
        for analysis
        in program.scope_analyses
        if (
            analysis.scope_id
            == "statement:0:root"
        )
    )

    assert (
        root.facts.source_tables
        == (
            "ods.loan_detail",
        )
    )

    assert (
        "dws.loan_summary"
        not in root.facts.source_tables
    )

    assert (
        root.facts.target_tables
        == ()
    )

    assert (
        program
        .statements[0]
        .write_target
        is not None
    )

    assert (
        program
        .statements[0]
        .write_target
        .table_name
        == "dws.loan_summary"
    )


def test_nested_subquery_scope_is_preserved():
    program = _analyze_scopes(
        """
        SELECT *
        FROM (
            SELECT id
            FROM ods.loan_detail
        ) nested_data
        """
    )

    physical_scope = next(
        analysis
        for analysis
        in program.scope_analyses
        if (
            "ods.loan_detail"
            in analysis.facts.source_tables
        )
    )

    assert (
        physical_scope.scope_id
        != "statement:0:root"
    )


def test_cte_scope_id_matches_cte_node():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id
            FROM ods.loan_detail
        )
        SELECT *
        FROM base
        """
    )

    node = next(
        node
        for node
        in program.cte_nodes
        if node.name == "base"
    )

    analysis = _scope_by_cte(
        program,
        "base",
    )

    assert (
        analysis.scope_id
        == node.scope_id
    )


def test_multiple_statements_have_separate_roots():
    program = _analyze_scopes(
        """
        INSERT OVERWRITE TABLE dws.a
        SELECT id FROM ods.a;

        INSERT OVERWRITE TABLE dws.b
        SELECT id FROM ods.b;
        """
    )

    root_ids = {
        analysis.scope_id
        for analysis
        in program.scope_analyses
        if analysis.scope_id.endswith(
            ":root"
        )
    }

    assert root_ids == {
        "statement:0:root",
        "statement:1:root",
    }



def test_scope_preserves_physical_and_cte_bindings():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id
            FROM ods.loan_detail
        ),
        joined_data AS (
            SELECT
                l.id
            FROM ods.loan_ext l
            JOIN base b
              ON l.id = b.id
        )
        SELECT *
        FROM joined_data
        """
    )

    base_scope = _scope_by_cte(
        program,
        "base",
    )

    joined_scope = _scope_by_cte(
        program,
        "joined_data",
    )

    bindings = {
        item.alias: item
        for item
        in joined_scope.source_bindings
    }

    assert (
        bindings["l"].physical_table
        == "ods.loan_ext"
    )

    assert (
        bindings["l"].source_scope_id
        is None
    )

    assert (
        bindings["b"].physical_table
        is None
    )

    assert (
        bindings["b"].source_scope_id
        == base_scope.scope_id
    )


def test_single_cte_source_is_preserved_as_scope_binding():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id
            FROM ods.loan_detail
        ),
        summary AS (
            SELECT id
            FROM base
        )
        SELECT *
        FROM summary
        """
    )

    base_scope = _scope_by_cte(
        program,
        "base",
    )

    summary_scope = _scope_by_cte(
        program,
        "summary",
    )

    assert len(
        summary_scope.source_bindings
    ) == 1

    binding = (
        summary_scope
        .source_bindings[0]
    )

    assert binding.alias == "base"

    assert (
        binding.physical_table
        is None
    )

    assert (
        binding.source_scope_id
        == base_scope.scope_id
    )
    

def test_scope_preserves_physical_source_binding():
    program = _analyze_scopes(
        """
        SELECT
            l.id,
            l.amount
        FROM ods.loan_detail l
        """
    )

    root = next(
        scope
        for scope
        in program.scope_analyses
        if (
            scope.scope_id
            == "statement:0:root"
        )
    )

    assert len(
        root.source_bindings
    ) == 1

    binding = (
        root.source_bindings[0]
    )

    assert (
        binding.alias
        == "l"
    )

    assert (
        binding.kind
        is (
            SourceBindingKind
            .PHYSICAL_TABLE
        )
    )

    assert (
        binding.physical_table
        == "ods.loan_detail"
    )

    assert (
        binding.source_scope_id
        is None
    )


def test_scope_preserves_cte_source_binding():
    program = _analyze_scopes(
        """
        WITH base AS (
            SELECT id
            FROM ods.loan_detail
        )
        SELECT b.id
        FROM base b
        """
    )

    base_scope = next(
        scope
        for scope
        in program.scope_analyses
        if (
            scope.cte_name
            == "base"
        )
    )

    root = next(
        scope
        for scope
        in program.scope_analyses
        if (
            scope.scope_id
            == "statement:0:root"
        )
    )

    assert len(
        root.source_bindings
    ) == 1

    binding = (
        root.source_bindings[0]
    )

    assert binding.alias == "b"

    assert (
        binding.kind
        is SourceBindingKind.SCOPE
    )

    assert (
        binding.physical_table
        is None
    )

    assert (
        binding.source_scope_id
        == base_scope.scope_id
    )