from __future__ import annotations

import pytest

from sql_pilot_engine.program.enums import (
    ProgramAnalysisStatus,
)
from sql_pilot_engine.program.models import (
    ParameterBinding,
    PartitionBinding,
    ProgramAnalysisResult,
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