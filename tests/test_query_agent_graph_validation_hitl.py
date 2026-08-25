from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)

from sql_pilot_engine.context.semantic.models import (
    SemanticColumn,
    SemanticModel,
    SemanticTable,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)

from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)


class EmptyRetriever:

    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
    ):
        return []


class FixedPlanner:

    def plan(
        self,
        *,
        query_context,
    ):

        return QueryPlan(
            tables=(
                "ods_hd_100_cldkxx",
            ),
            dimensions=(),
            metrics=(
                "tech_loan_balance",
            ),
            filters=(
                "is_high_tech_mfg_loan_code = '1'",
            ),
            group_by=(),
        )


@dataclass(frozen=True)
class FakeGeneratedSQL:
    sql: str


class FakeSQLGenerator:

    def generate(
        self,
        **kwargs,
    ):

        return FakeGeneratedSQL(
            sql=(
                "SELECT "
                "SUM(loan_bal_rmb) "
                "FROM ods_hd_100_cldkxx "
                "WHERE "
                "is_high_tech_mfg_loan_code = '1'"
            )
        )


@dataclass(frozen=True)
class FakeTrustResult:
    success: bool
    final_status: str
    trusted_sql: str | None = None
    error_message: str | None = None
    missing_context: tuple[str, ...] = ()


class ContextAwareTrustedSQLWorkflow:

    def run(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
        query_context=None,
    ) -> FakeTrustResult:

        _ = dialect

        assert query_context is not None

        if not (
            query_context.session_context
        ):
            return FakeTrustResult(
                success=False,
                final_status=(
                    "context_required"
                ),
                trusted_sql=None,
                error_message=(
                    "同比口径尚未确认。"
                ),
                missing_context=(
                    "同比统计口径",
                ),
            )

        assert (
            "按上年同月"
            in query_context
            .session_context[-1]
        )

        return FakeTrustResult(
            success=True,
            final_status="no_issue",
            trusted_sql=sql,
        )


def build_semantic_model(
) -> SemanticModel:

    return SemanticModel(
        tables=(
            SemanticTable(
                name=(
                    "ods_hd_100_cldkxx"
                ),
                description=(
                    "科技贷款明细宽表"
                ),
                columns=(
                    SemanticColumn(
                        name=(
                            "loan_bal_rmb"
                        ),
                        description=(
                            "贷款余额"
                        ),
                        data_type=(
                            "DECIMAL(22,2)"
                        ),
                    ),
                ),
            ),
        ),
        metrics=(),
    )


def test_trusted_sql_context_required_uses_runtime_hitl():

    graph = QueryAgentGraph(
        semantic_model=(
            build_semantic_model()
        ),
        knowledge_retriever=(
            EmptyRetriever()
        ),
        verified_sql_retriever=(
            EmptyRetriever()
        ),
        context_builder=(
            QueryContextBuilder()
        ),
        planner=FixedPlanner(),
        sql_generator=(
            FakeSQLGenerator()
        ),
        trusted_sql_workflow=(
            ContextAwareTrustedSQLWorkflow()
        ),
        checkpoint_store=(
            MemoryCheckpointStore()
        ),
        semantic_validator=None,
    )

    thread_id = (
        "trusted-sql-hitl-test"
    )

    first = graph.start(
        thread_id=thread_id,
        question=(
            "统计高新技术企业"
            "贷款余额同比"
        ),
    )

    assert "__interrupt__" in first

    payload = (
        first["__interrupt__"][0]
        .value
    )

    assert payload[
        "missing_context"
    ] == (
        "同比统计口径",
    )

    first_turn_id = (
        first["turn_id"]
    )

    second = graph.resume(
        thread_id=thread_id,
        answer=(
            "同比按上年同月计算。"
        ),
    )

    assert (
        "__interrupt__"
        not in second
    )

    assert (
        second["turn_id"]
        == first_turn_id
    )

    assert second[
        "session_context"
    ] == (
        (
            "User clarification: "
            "同比按上年同月计算。"
        ),
    )

    assert (
        second["trusted_sql"]
        is not None
    )

    assert (
        second["success"]
        is True
    )