from __future__ import annotations

import pytest

from sql_pilot_engine.analysis.sql_parser import (
    SQLParser,
)
from sql_pilot_engine.program.builder import (
    ProgramBuilder,
)
from sql_pilot_engine.program.enums import (
    StatementKind,
    WriteStrategy,
)
from sql_pilot_engine.program.preprocessing import (
    preprocess_program_sql,
)


def _build_program(
    raw_sql: str,
):
    preprocess_result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    parse_result = (
        SQLParser().parse(
            preprocess_result
            .normalized_sql,
            dialect="maxcompute",
        )
    )

    assert (
        parse_result.success
        is True
    ), parse_result.error_message

    return (
        ProgramBuilder().build(
            preprocess_result=(
                preprocess_result
            ),
            parse_result=parse_result,
        )
    )


def test_select_statement_is_built():
    program = _build_program(
        "SELECT id "
        "FROM loan_table"
    )

    assert len(
        program.statements
    ) == 1

    statement = (
        program.statements[0]
    )

    assert (
        statement.index
        == 0
    )

    assert (
        statement.kind
        is StatementKind.SELECT
    )

    assert (
        statement.write_target
        is None
    )


def test_insert_overwrite_target_is_built():
    program = _build_program(
        "INSERT OVERWRITE TABLE "
        "dws.loan_summary "
        "SELECT id "
        "FROM ods.loan_detail"
    )

    statement = (
        program.statements[0]
    )

    assert (
        statement.kind
        is StatementKind.INSERT_OVERWRITE
    )

    target = (
        statement.write_target
    )

    assert target is not None

    assert (
        target.table_name
        == "dws.loan_summary"
    )

    assert (
        target.strategy
        is WriteStrategy.OVERWRITE
    )


def test_insert_into_uses_append_strategy():
    program = _build_program(
        "INSERT INTO TABLE "
        "dws.loan_summary "
        "SELECT id "
        "FROM ods.loan_detail"
    )

    target = (
        program
        .statements[0]
        .write_target
    )

    assert target is not None

    assert (
        target.strategy
        is WriteStrategy.APPEND
    )


def test_static_partition_is_built():
    program = _build_program(
        "INSERT OVERWRITE TABLE "
        "dws.loan_summary "
        "PARTITION(dt='202609') "
        "SELECT id "
        "FROM ods.loan_detail"
    )

    target = (
        program
        .statements[0]
        .write_target
    )

    assert target is not None

    assert len(
        target.partition_spec
    ) == 1

    partition = (
        target.partition_spec[0]
    )

    assert (
        partition.name
        == "dt"
    )

    assert (
        partition.value
        == "'202609'"
    )

    assert (
        partition.is_dynamic
        is False
    )


def test_dynamic_partition_is_built():
    program = _build_program(
        "INSERT OVERWRITE TABLE "
        "dws.loan_summary "
        "PARTITION(dt) "
        "SELECT id, dt "
        "FROM ods.loan_detail"
    )

    target = (
        program
        .statements[0]
        .write_target
    )

    assert target is not None

    partition = (
        target.partition_spec[0]
    )

    assert (
        partition.name
        == "dt"
    )

    assert (
        partition.value
        is None
    )

    assert (
        partition.is_dynamic
        is True
    )


def test_ctes_are_projected_into_program():
    program = _build_program(
        "WITH base AS ("
        "    SELECT id "
        "    FROM ods.loan_detail"
        "), "
        "summary AS ("
        "    SELECT id "
        "    FROM base"
        ") "
        "SELECT * "
        "FROM summary"
    )

    assert (
        program
        .statements[0]
        .cte_names
        == (
            "base",
            "summary",
        )
    )

    assert tuple(
        node.name
        for node
        in program.cte_nodes
    ) == (
        "base",
        "summary",
    )

    # B2 还没有进入 Dependency Analysis。
    assert all(
        node.dependency_scope_ids
        == ()
        for node
        in program.cte_nodes
    )


def test_same_parameter_is_grouped():
    raw_sql = (
        "SELECT * "
        "FROM ods.loan_detail "
        "WHERE dt='${p_month}' "
        "AND report_month="
        "'${p_month}'"
    )

    program = _build_program(
        raw_sql
    )

    assert len(
        program.parameters
    ) == 1

    parameter = (
        program.parameters[0]
    )

    assert (
        parameter.name
        == "p_month"
    )

    assert len(
        parameter.occurrences
    ) == 2




def test_different_parameters_remain_separate():
    raw_sql = (
        "SELECT * "
        "FROM ods.loan_detail "
        "WHERE dt='${p_month}' "
        "AND org_code="
        "'${p_org}'"
    )

    program = _build_program(
        raw_sql
    )

    assert tuple(
        parameter.name
        for parameter
        in program.parameters
    ) == (
        "p_month",
        "p_org",
    )


def test_multiple_statements_are_preserved():
    raw_sql = (
        "INSERT OVERWRITE TABLE dws.a "
        "SELECT id FROM ods.a;"
        "\n"
        "INSERT OVERWRITE TABLE dws.b "
        "SELECT id FROM ods.b;"
    )

    program = _build_program(
        raw_sql
    )

    assert len(
        program.statements
    ) == 2

    assert tuple(
        statement.index
        for statement
        in program.statements
    ) == (
        0,
        1,
    )

    assert tuple(
        statement.kind
        for statement
        in program.statements
    ) == (
        StatementKind.INSERT_OVERWRITE,
        StatementKind.INSERT_OVERWRITE,
    )


def test_builder_rejects_failed_parse():
    raw_sql = (
        "SELECT FROM"
    )

    preprocess_result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    parse_result = (
        SQLParser().parse(
            preprocess_result
            .normalized_sql,
            dialect="maxcompute",
        )
    )

    assert (
        parse_result.success
        is False
    )

    with pytest.raises(
        ValueError,
        match="failed parse result",
    ):
        ProgramBuilder().build(
            preprocess_result=(
                preprocess_result
            ),
            parse_result=parse_result,
        )