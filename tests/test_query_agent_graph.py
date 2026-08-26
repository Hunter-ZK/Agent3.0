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
from sql_pilot_engine.linking.models import (
    LinkedSchema,
    LinkedTable,
)

from sql_pilot_engine.metadata.models import (
    TableMetadata,
)

class PassingSchemaLinker:
    """
    Graph 单测只验证 Runtime 编排，
    不重复测试真实 SchemaLinker。

    SchemaLinker 本身由
    tests/test_schema_linker.py
    单独负责测试。
    """

    def link(
        self,
        *,
        plan,
    ) -> LinkedSchema:

        return LinkedSchema(
            tables=tuple(
                LinkedTable(
                    metadata=(
                        TableMetadata(
                            full_name=(
                                table_name
                            ),
                            columns={},
                        )
                    )
                )
                for table_name
                in plan.tables
            ),
        )


class EmptyRetriever:
    def retrieve(self, *, question: str, top_k: int):
        return []


class ReadyPlanner:
    def plan(self, *, query_context) -> QueryPlan:
        assert query_context.semantic_context
        return QueryPlan(
            tables=("dwd_hd_201_cldwdk",),
            dimensions=(),
            metrics=("green_loan_balance",),
            filters=("dt = '${p_month_yyyymm}'",),
            group_by=(),
        )


class ClarificationPlanner:
    def plan(self, *, query_context):
        return PlanningClarification(
            clarification_question="请确认科技贷款还是绿色贷款。",
            missing_context=("贷款业务主题",),
            reason="当前存在多个合理业务主题。",
        )


@dataclass(frozen=True)
class FakeGeneratedSQL:
    sql: str


class FakeSQLGenerator:
    def generate(self, **kwargs):
        assert kwargs["query_context"].semantic_context
        return FakeGeneratedSQL(
            sql=(
                "SELECT SUM(loan_bal_rmb) "
                "FROM dwd_hd_201_cldwdk "
                "WHERE dt = '${p_month_yyyymm}'"
            )
        )


class ShouldNotGenerateSQL:
    def generate(self, **kwargs):
        raise AssertionError(
            "Generator must not run when clarification is required."
        )


@dataclass(frozen=True)
class FakeValidationResult:
    success: bool
    final_status: str
    final_sql: str | None = None
    trusted_sql: str | None = None
    
    error_message: str | None = None
    fix_response: object | None = None
    missing_context: tuple[str, ...] = ()


class PassingValidationWorkflow:

    def run(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
        query_context=None,
    ):
        _ = dialect

        assert query_context is not None
        assert query_context.question

        return FakeValidationResult(
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


def build_graph(*, planner, generator) -> QueryAgentGraph:
    return QueryAgentGraph(
        semantic_model=build_semantic_model(),
        knowledge_retriever=EmptyRetriever(),
        verified_sql_retriever=EmptyRetriever(),
        context_builder=QueryContextBuilder(),
        planner=planner,
        schema_linker=PassingSchemaLinker(),
        sql_generator=generator,
        trusted_sql_workflow=PassingValidationWorkflow(),
        checkpoint_store=MemoryCheckpointStore(),
        semantic_validator=None,
        max_semantic_retries=1,
    )


def test_graph_runs_happy_path():
    graph = build_graph(
        planner=ReadyPlanner(),
        generator=FakeSQLGenerator(),
    )

    state = graph.start(
        thread_id="graph-happy-path",
        question="统计本期绿色贷款余额",
    )

    assert state["query_plan"].tables == (
        "dwd_hd_201_cldwdk",
    )
    assert state["query_context"] is not None
    assert state["query_context"].semantic_context
    assert state["generated_sql"]
    assert state["candidate_sql"] is not None
    assert state["trusted_sql"] is not None
    assert state["success"] is True


def test_graph_stops_for_clarification():
    graph = build_graph(
        planner=ClarificationPlanner(),
        generator=ShouldNotGenerateSQL(),
    )

    state = graph.start(
        thread_id="graph-clarification",
        question="统计本期贷款余额",
    )

    assert "__interrupt__" in state
    payload = state["__interrupt__"][0].value

    assert (
        payload["question"]
        == "请确认科技贷款还是绿色贷款。"
    )
    assert payload["missing_context"] == ("贷款业务主题",)
    assert state["generated_sql"] is None
