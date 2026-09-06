from __future__ import annotations

from dataclasses import replace

import pytest

from sql_pilot_engine.analysis.sql_parser import (
    SQLParser,
)
from sql_pilot_engine.program.builder import (
    ProgramBuilder,
)
from sql_pilot_engine.program.cte_dependencies import (
    CTEDependencyResolver,
)
from sql_pilot_engine.program.preprocessing import (
    preprocess_program_sql,
)
from sql_pilot_engine.program.scope_resolver import (
    ScopeResolver,
)


def _analyze(
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

    program = (
        ScopeResolver().resolve(
            program=program,
            parse_result=parse_result,
        )
    )

    program = (
        CTEDependencyResolver()
        .resolve(
            program=program,
            parse_result=parse_result,
        )
    )

    return (
        program,
        parse_result,
    )


def _node(
    program,
    name: str,
):
    return next(
        node
        for node
        in program.cte_nodes
        if node.name == name
    )


def test_simple_cte_chain():
    program, _ = _analyze(
        """
        WITH base AS (
            SELECT id
            FROM ods.loan_detail
        ),
        summary AS (
            SELECT id
            FROM base
        ),
        final_data AS (
            SELECT id
            FROM summary
        )
        SELECT *
        FROM final_data
        """
    )

    base = _node(
        program,
        "base",
    )

    summary = _node(
        program,
        "summary",
    )

    final_data = _node(
        program,
        "final_data",
    )

    assert (
        base.dependency_scope_ids
        == ()
    )

    assert (
        summary.dependency_scope_ids
        == (
            base.scope_id,
        )
    )

    assert (
        final_data.dependency_scope_ids
        == (
            summary.scope_id,
        )
    )


def test_physical_table_is_not_cte_dependency():
    program, _ = _analyze(
        """
        WITH base AS (
            SELECT id
            FROM ods.loan_detail
        )
        SELECT *
        FROM base
        """
    )

    base = _node(
        program,
        "base",
    )

    assert (
        base.dependency_scope_ids
        == ()
    )


def test_cte_can_depend_on_multiple_ctes():
    program, _ = _analyze(
        """
        WITH loan AS (
            SELECT id
            FROM ods.loan
        ),
        customer AS (
            SELECT id
            FROM ods.customer
        ),
        joined AS (
            SELECT
                l.id
            FROM loan l
            JOIN customer c
              ON l.id = c.id
        )
        SELECT *
        FROM joined
        """
    )

    loan = _node(
        program,
        "loan",
    )

    customer = _node(
        program,
        "customer",
    )

    joined = _node(
        program,
        "joined",
    )

    assert (
        joined.dependency_scope_ids
        == (
            loan.scope_id,
            customer.scope_id,
        )
    )


def test_dependency_inside_nested_subquery_is_preserved():
    program, _ = _analyze(
        """
        WITH base AS (
            SELECT id
            FROM ods.loan
        ),
        filtered AS (
            SELECT id
            FROM (
                SELECT id
                FROM base
            ) nested_base
        )
        SELECT *
        FROM filtered
        """
    )

    base = _node(
        program,
        "base",
    )

    filtered = _node(
        program,
        "filtered",
    )

    assert (
        filtered.dependency_scope_ids
        == (
            base.scope_id,
        )
    )


def test_transitive_dependencies_are_not_duplicated():
    program, _ = _analyze(
        """
        WITH a AS (
            SELECT id
            FROM ods.a
        ),
        b AS (
            SELECT id
            FROM a
        ),
        c AS (
            SELECT id
            FROM b
        )
        SELECT *
        FROM c
        """
    )

    a = _node(
        program,
        "a",
    )

    b = _node(
        program,
        "b",
    )

    c = _node(
        program,
        "c",
    )

    assert (
        b.dependency_scope_ids
        == (
            a.scope_id,
        )
    )

    assert (
        c.dependency_scope_ids
        == (
            b.scope_id,
        )
    )

    assert (
        a.scope_id
        not in c.dependency_scope_ids
    )


def test_topological_order_places_dependencies_first():
    program, _ = _analyze(
        """
        WITH a AS (
            SELECT id
            FROM ods.a
        ),
        b AS (
            SELECT id
            FROM a
        ),
        c AS (
            SELECT id
            FROM b
        )
        SELECT *
        FROM c
        """
    )

    order = (
        CTEDependencyResolver
        .topological_order(
            program=program,
            statement_index=0,
        )
    )

    names = tuple(
        next(
            node.name
            for node
            in program.cte_nodes
            if (
                node.scope_id
                == scope_id
            )
        )
        for scope_id
        in order
    )

    assert names == (
        "a",
        "b",
        "c",
    )


def test_multiple_statements_are_isolated():
    program, _ = _analyze(
        """
        WITH base AS (
            SELECT id
            FROM ods.a
        )
        INSERT OVERWRITE TABLE dws.a
        SELECT * FROM base;

        WITH base AS (
            SELECT id
            FROM ods.b
        )
        INSERT OVERWRITE TABLE dws.b
        SELECT * FROM base;
        """
    )

    first_nodes = tuple(
        node
        for node
        in program.cte_nodes
        if (
            node.statement_index
            == 0
        )
    )

    second_nodes = tuple(
        node
        for node
        in program.cte_nodes
        if (
            node.statement_index
            == 1
        )
    )

    assert len(
        first_nodes
    ) == 1

    assert len(
        second_nodes
    ) == 1

    assert (
        first_nodes[0].scope_id
        != second_nodes[0].scope_id
    )


def test_cycle_is_detected_by_topological_order():
    program, _ = _analyze(
        """
        WITH a AS (
            SELECT id
            FROM ods.a
        ),
        b AS (
            SELECT id
            FROM a
        )
        SELECT *
        FROM b
        """
    )

    a = _node(
        program,
        "a",
    )

    b = _node(
        program,
        "b",
    )

    cyclic_nodes = tuple(
        replace(
            node,
            dependency_scope_ids=(
                (b.scope_id,)
                if node.scope_id
                == a.scope_id
                else (a.scope_id,)
            ),
        )
        for node
        in program.cte_nodes
    )

    cyclic_program = replace(
        program,
        cte_nodes=cyclic_nodes,
    )

    with pytest.raises(
        ValueError,
        match="cycle detected",
    ):
        (
            CTEDependencyResolver
            .topological_order(
                program=(
                    cyclic_program
                ),
                statement_index=0,
            )
        )