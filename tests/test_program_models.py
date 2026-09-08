from __future__ import annotations

import pytest

from sql_pilot_engine.program.enums import (
    ProgramAnalysisStatus,
    SourceBindingKind,
)
from sql_pilot_engine.program.models import (
    ParameterBinding,
    PartitionBinding,
    ProgramAnalysisResult,
    ScopeSourceBinding,
    ScopeOutputProjection,
)


def test_parameter_binding_requires_occurrence():
    with pytest.raises(
        ValueError,
        match="at least one occurrence",
    ):
        ParameterBinding(
            name="p_month_yyyymm",
            occurrences=(),
        )


def test_partition_binding_dynamic_state_is_derived():
    dynamic_partition = (
        PartitionBinding(
            name="dt",
        )
    )

    static_partition = (
        PartitionBinding(
            name="dt",
            value="'202609'",
        )
    )

    assert (
        dynamic_partition.is_dynamic
        is True
    )

    assert (
        static_partition.is_dynamic
        is False
    )


def test_failed_result_requires_failure_reason():
    with pytest.raises(
        ValueError,
        match="failure_reason",
    ):
        ProgramAnalysisResult(
            status=(
                ProgramAnalysisStatus.FAILED
            ),
            program=None,
        )


def test_failed_result_cannot_contain_program():
    # 这里不需要构造真正 SQLProgram。
    #
    # 先传入任意非 None 对象，
    # 验证 FAILED 状态首先拒绝 program。
    with pytest.raises(
        ValueError,
        match="cannot contain a program",
    ):
        ProgramAnalysisResult(
            status=(
                ProgramAnalysisStatus.FAILED
            ),
            program=object(),  # type: ignore[arg-type]
            failure_reason="parse failed",
        )


def test_non_failed_result_requires_program():
    with pytest.raises(
        ValueError,
        match="must contain a program",
    ):
        ProgramAnalysisResult(
            status=(
                ProgramAnalysisStatus.COMPLETE
            ),
            program=None,
        )
        

def test_physical_source_binding_requires_table():
    with pytest.raises(
        ValueError,
        match="requires physical_table",
    ):
        ScopeSourceBinding(
            alias="a",
            kind=(
                SourceBindingKind
                .PHYSICAL_TABLE
            ),
        )


def test_scope_source_binding_requires_scope_id():
    with pytest.raises(
        ValueError,
        match="requires source_scope_id",
    ):
        ScopeSourceBinding(
            alias="a",
            kind=(
                SourceBindingKind.SCOPE
            ),
        )


def test_unresolved_source_binding_requires_reason():
    with pytest.raises(
        ValueError,
        match="requires unresolved_reason",
    ):
        ScopeSourceBinding(
            alias="a",
            kind=(
                SourceBindingKind
                .UNRESOLVED
            ),
        )


def test_unresolved_source_binding_keeps_explicit_reason():
    binding = ScopeSourceBinding(
        alias="  Unknown_Alias  ",
        kind=(
            SourceBindingKind
            .UNRESOLVED
        ),
        unresolved_reason=(
            "Unsupported source type."
        ),
    )

    assert (
        binding.alias
        == "unknown_alias"
    )

    assert (
        binding.physical_table
        is None
    )

    assert (
        binding.source_scope_id
        is None
    )

    assert (
        binding.unresolved_reason
        == "Unsupported source type."
    )
    

def test_output_projection_normalizes_names():
    projection = (
        ScopeOutputProjection(
            column_names=(
                "ID",
                " Total_Amount ",
            ),
        )
    )

    assert (
        projection.column_names
        == (
            "id",
            "total_amount",
        )
    )

    assert (
        projection.complete
        is True
    )


def test_output_projection_with_wildcard_is_incomplete():
    projection = (
        ScopeOutputProjection(
            column_names=(
                "id",
            ),
            has_wildcard=True,
        )
    )

    assert (
        projection.complete
        is False
    )


def test_output_projection_with_unnamed_expression_is_incomplete():
    projection = (
        ScopeOutputProjection(
            column_names=(
                "id",
            ),
            unnamed_expression_count=1,
        )
    )

    assert (
        projection.complete
        is False
    )