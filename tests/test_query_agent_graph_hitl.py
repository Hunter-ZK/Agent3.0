from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.builder import QueryContextBuilder
from sql_pilot_engine.context.semantic.models import (
    SemanticColumn,
    SemanticModel,
    SemanticTable,
)
from sql_pilot_engine.generation.models import (
    PlanningClarification,
    QueryPlan,
)
from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)
from sql_pilot_engine.runtime.query_graph import QueryAgentGraph


class EmptyRetriever:
    def retrieve(self, *, question: str, top_k: int):
        return []


class InteractivePlanner:
    def plan(self, *, query_context):
        if not query_context.session_context:
            return PlanningClarification(
                clarification_question="请确认科技贷款还是绿色贷款。",
                missing_context=("贷款业务主题",),
                reason="当前存在多个合理业务主题。",
            )

        assert "绿色贷款" in query_context.session_context[-1]

        return QueryPlan(
            tables=("dwd_hd_201_cldwdk",),
            dimensions=(),
            metrics=("green_loan_balance",),
            filters=("dt = '${p_month_yyyymm}'",),
            group_by=(),
        )


class AlwaysClarifyPlanner:
    def plan(self, *, query_context):
        return PlanningClarification(
            clarification_question="仍缺少必要业务信息，请继续补充。",
            missing_context=("必要业务信息",),
            reason="当前 Context 仍不足。",
        )


@dataclass(frozen=True)
class FakeGeneratedSQL:
    sql: str


class FakeSQLGenerator:
    def generate(self, **kwargs):
        return FakeGeneratedSQL(
            sql=(
                "SELECT SUM(loan_bal_rmb) "
                "FROM dwd_hd_201_cldwdk "
                "WHERE dt = '${p_month_yyyymm}'"
            )
        )


@dataclass(frozen=True)
class FakeTrustedSQLResult:
    success: bool
    final_status: str
    final_sql: str | None = None
    trusted_sql: str | None = None
    
    error_message: str | None = None
    fix_response: object | None = None
    missing_context: tuple[str, ...] = ()


class PassingTrustedSQLWorkflow:
    def run(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
        query_context = None,
    ):
        _ = dialect

        return FakeTrustedSQLResult(
            success=True,
            final_status="no_issue",
            final_sql=sql,
            trusted_sql=sql,
        )

def build_semantic_model() -> SemanticModel:
    return SemanticModel(
        tables=(
            SemanticTable(
                name="dwd_hd_201_cldwdk",
                description="绿色单位贷款明细宽表",
                columns=(
                    SemanticColumn(
                        name="loan_bal_rmb",
                        description="贷款余额",
                        data_type="DECIMAL(22,2)",
                    ),
                    SemanticColumn(
                        name="dt",
                        description="统计期",
                        data_type="STRING",
                    ),
                ),
            ),
        ),
        metrics=(),
    )


def build_graph(
    *,
    planner,
    max_clarification_rounds: int = 3,
) -> QueryAgentGraph:
    return QueryAgentGraph(
        semantic_model=build_semantic_model(),
        knowledge_retriever=EmptyRetriever(),
        verified_sql_retriever=EmptyRetriever(),
        context_builder=QueryContextBuilder(),
        planner=planner,
        sql_generator=FakeSQLGenerator(),
        trusted_sql_workflow=PassingTrustedSQLWorkflow(),
        checkpoint_store=MemoryCheckpointStore(),
        semantic_validator=None,
        max_semantic_retries=1,
        max_clarification_rounds=max_clarification_rounds,
    )


def test_graph_interrupts_and_resumes():
    graph = build_graph(
        planner=InteractivePlanner(),
    )
    thread_id = "hitl-test-thread"

    first = graph.start(
        thread_id=thread_id,
        question="统计本期贷款余额",
    )

    assert "__interrupt__" in first
    payload = first["__interrupt__"][0].value
    assert payload["question"] == "请确认科技贷款还是绿色贷款。"
    assert first["generated_sql"] is None

    second = graph.resume(
        thread_id=thread_id,
        answer="这次统计绿色贷款。",
    )

    assert "__interrupt__" not in second
    assert second["query_plan"].tables == (
        "dwd_hd_201_cldwdk",
    )
    assert second["query_plan"].metrics == (
        "green_loan_balance",
    )
    assert second["session_context"] == (
        "User clarification: 这次统计绿色贷款。",
    )
    assert second["clarification_round"] == 1
    assert second["candidate_sql"] is not None
    assert second["trusted_sql"] is not None
    assert second["success"] is True


def test_graph_stops_after_max_clarification_rounds():
    graph = build_graph(
        planner=AlwaysClarifyPlanner(),
        max_clarification_rounds=2,
    )
    thread_id = "clarification-limit-thread"

    first = graph.start(
        thread_id=thread_id,
        question="统计贷款余额",
    )
    assert "__interrupt__" in first
    assert first["__interrupt__"][0].value["round"] == 1

    second = graph.resume(
        thread_id=thread_id,
        answer="先按绿色贷款理解。",
    )
    assert "__interrupt__" in second
    assert second["__interrupt__"][0].value["round"] == 2
    assert second["clarification_round"] == 1

    third = graph.resume(
        thread_id=thread_id,
        answer="没有更多信息可以补充。",
    )

    assert "__interrupt__" not in third
    assert third["clarification_round"] == 2
    assert third["success"] is False
    assert third.get("trusted_sql") is None
    assert "连续多次" in third["error_message"]
