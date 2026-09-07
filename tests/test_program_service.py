from __future__ import annotations

from dataclasses import replace

from sql_pilot_engine.program.enums import (
    ProgramAnalysisStatus,
    SourceBindingKind,
    StatementKind,
    WriteStrategy,
)

from sql_pilot_engine.program.models import (
    ScopeSourceBinding,
)

from sql_pilot_engine.program.scope_resolver import (
    ScopeResolver,
)

from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)

class _UnresolvedSourceScopeResolver:
    """
    测试专用 Resolver。

    先执行真实 ScopeResolver，
    再人为注入一个 UNRESOLVED binding。

    目的不是测试 SQLGlot，
    而是验证 ProgramAnalysisService 的
    PARTIAL 状态聚合 Contract。
    """

    def __init__(
        self,
    ) -> None:
        self._delegate = (
            ScopeResolver()
        )

    def resolve(
        self,
        *,
        program,
        parse_result,
    ):
        resolved = (
            self
            ._delegate
            .resolve(
                program=program,
                parse_result=parse_result,
            )
        )

        first_scope = (
            resolved
            .scope_analyses[0]
        )

        degraded_scope = replace(
            first_scope,
            source_bindings=(
                first_scope
                .source_bindings
                + (
                    ScopeSourceBinding(
                        alias=(
                            "unknown_source"
                        ),
                        kind=(
                            SourceBindingKind
                            .UNRESOLVED
                        ),
                        unresolved_reason=(
                            "Test unresolved "
                            "source."
                        ),
                    ),
                )
            ),
        )

        return replace(
            resolved,
            scope_analyses=(
                (
                    degraded_scope,
                )
                + (
                    resolved
                    .scope_analyses[1:]
                )
            ),
        )

def test_simple_query_analysis_is_complete():
    result = (
        ProgramAnalysisService()
        .analyze(
            """
            SELECT
                id,
                amount
            FROM ods.loan_detail
            """
        )
    )

    assert (
        result.status
        is ProgramAnalysisStatus.COMPLETE
    )

    assert result.program is not None

    assert len(
        result.program.statements
    ) == 1

    assert (
        result
        .program
        .statements[0]
        .kind
        is StatementKind.SELECT
    )


def test_program_analysis_preserves_session_hint():
    result = (
        ProgramAnalysisService()
        .analyze(
            """
            SET odps.instance.priority=7;

            SELECT id
            FROM ods.loan_detail
            """
        )
    )

    assert result.program is not None

    assert len(
        result
        .program
        .session_hints
    ) == 1

    assert (
        result
        .program
        .session_hints[0]
        .name
        == "odps.instance.priority"
    )


def test_program_analysis_groups_parameters():
    result = (
        ProgramAnalysisService()
        .analyze(
            """
            SELECT *
            FROM ods.loan_detail
            WHERE dt='${p_month}'
              AND report_month='${p_month}'
            """
        )
    )

    assert result.program is not None

    assert len(
        result.program.parameters
    ) == 1

    parameter = (
        result.program.parameters[0]
    )

    assert (
        parameter.name
        == "p_month"
    )

    assert len(
        parameter.occurrences
    ) == 2


def test_insert_target_is_available():
    result = (
        ProgramAnalysisService()
        .analyze(
            """
            INSERT OVERWRITE TABLE
                dws.loan_summary
            PARTITION(dt='202609')
            SELECT
                id
            FROM ods.loan_detail
            """
        )
    )

    assert result.program is not None

    statement = (
        result.program.statements[0]
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


def test_cte_dependencies_are_available():
    result = (
        ProgramAnalysisService()
        .analyze(
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
    )

    assert result.program is not None

    nodes = {
        node.name: node
        for node
        in result.program.cte_nodes
    }

    assert (
        nodes["base"]
        .dependency_scope_ids
        == ()
    )

    assert (
        nodes["summary"]
        .dependency_scope_ids
        == (
            nodes["base"].scope_id,
        )
    )

    assert (
        nodes["final_data"]
        .dependency_scope_ids
        == (
            nodes["summary"].scope_id,
        )
    )


def test_scope_analysis_distinguishes_physical_table():
    result = (
        ProgramAnalysisService()
        .analyze(
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
    )

    assert result.program is not None

    base_scope = next(
        scope
        for scope
        in result.program.scope_analyses
        if scope.cte_name == "base"
    )

    summary_scope = next(
        scope
        for scope
        in result.program.scope_analyses
        if scope.cte_name == "summary"
    )

    assert (
        base_scope.facts.source_tables
        == (
            "ods.loan_detail",
        )
    )

    assert (
        summary_scope
        .facts
        .source_tables
        == ()
    )


def test_invalid_sql_returns_failed_result():
    result = (
        ProgramAnalysisService()
        .analyze(
            "SELECT FROM"
        )
    )

    assert (
        result.status
        is ProgramAnalysisStatus.FAILED
    )

    assert (
        result.program
        is None
    )

    assert (
        result.failure_reason
        is not None
    )


def test_empty_sql_returns_failed_result():
    result = (
        ProgramAnalysisService()
        .analyze(
            "   \n   "
        )
    )

    assert (
        result.status
        is ProgramAnalysisStatus.FAILED
    )

    assert result.program is None


def test_set_only_program_returns_failed_result():
    result = (
        ProgramAnalysisService()
        .analyze(
            """
            SET odps.instance.priority=7;
            """
        )
    )

    assert (
        result.status
        is ProgramAnalysisStatus.FAILED
    )

    assert result.program is None
    
def test_unresolved_source_binding_downgrades_program_to_partial():
    service = (
        ProgramAnalysisService(
            scope_resolver=(
                _UnresolvedSourceScopeResolver()
            )
        )
    )

    result = service.analyze(
        """
        SELECT id
        FROM ods.loan_detail
        """
    )

    assert (
        result.status
        is ProgramAnalysisStatus.PARTIAL
    )

    assert result.program is not None

    assert result.diagnostics

    assert any(
        (
            "unknown_source"
            in diagnostic
        )
        for diagnostic
        in result.diagnostics
    )