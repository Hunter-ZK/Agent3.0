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
    PlanningClarification,
    QueryPlan,
)
from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)


# ============================================================
# Fakes
# ============================================================


class EmptyRetriever:
    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
    ):
        return []


class ReadyPlanner:
    def plan(
        self,
        **kwargs,
    ) -> QueryPlan:

        return QueryPlan(
            tables=(
                "dwd_hd_201_cldwdk",
            ),

            dimensions=(),

            metrics=(
                "green_loan_balance",
            ),

            filters=(
                "dt = '${p_month_yyyymm}'",
            ),

            group_by=(),
        )


class ClarificationPlanner:
    def plan(
        self,
        **kwargs,
    ):
        return PlanningClarification(
            clarification_question=(
                "请确认科技贷款还是绿色贷款。"
            ),

            missing_context=(
                "贷款业务主题",
            ),

            reason=(
                "当前存在多个合理业务主题。"
            ),
        )


@dataclass(
    frozen=True,
)
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
                "FROM dwd_hd_201_cldwdk "
                "WHERE "
                "dt = '${p_month_yyyymm}'"
            )
        )


@dataclass(
    frozen=True,
)
class FakeValidationResult:
    success: bool
    final_status: str
    fix_response: object | None = None


class PassingValidationWorkflow:
    def run(
        self,
        sql: str,
    ):
        return FakeValidationResult(
            success=True,
            final_status="no_issue",
        )


class ShouldNotGenerateSQL:
    def generate(
        self,
        **kwargs,
    ):
        raise AssertionError(
            "Generator must not run "
            "when Planner requests "
            "clarification."
        )


# ============================================================
# Fixtures
# ============================================================


def build_semantic_model():
    return SemanticModel(
        tables=(
            SemanticTable(
                name=(
                    "dwd_hd_201_cldwdk"
                ),

                description=(
                    "绿色单位贷款明细宽表"
                ),

                columns=(
                    SemanticColumn(
                        name="loan_bal_rmb",
                        description="贷款余额",
                        data_type=(
                            "DECIMAL(22,2)"
                        ),
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


# ============================================================
# Tests
# ============================================================


def test_graph_runs_happy_path():
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

        planner=ReadyPlanner(),

        sql_generator=(
            FakeSQLGenerator()
        ),

        validation_workflow=(
            PassingValidationWorkflow()
        ),

        # V0.1先测试：
        # 无Semantic Validator时
        # deterministic validation通过即可。
        semantic_validator=None,

        max_semantic_retries=1,
    )

    state = graph.invoke(
        question=(
            "统计本期绿色贷款余额"
        )
    )

    assert (
        state["query_plan"].tables
        == (
            "dwd_hd_201_cldwdk",
        )
    )

    assert (
        state["generated_sql"]
    )

    assert (
        state["candidate_sql"]
        is not None
    )


def test_graph_stops_for_clarification():
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

        planner=(
            ClarificationPlanner()
        ),

        sql_generator=(
            ShouldNotGenerateSQL()
        ),

        validation_workflow=(
            PassingValidationWorkflow()
        ),

        semantic_validator=None,

        max_semantic_retries=1,
    )

    state = graph.start(
        thread_id="aaaaa",
        question=(
            "统计本期贷款余额"
        )
    )

    assert (
        state[
            "clarification_question"
        ]
        == (
            "请确认科技贷款还是绿色贷款。"
        )
    )

    assert state["missing_context"] == (
        "贷款业务主题",
    )

    assert (
        "generated_sql"
        not in state
    )