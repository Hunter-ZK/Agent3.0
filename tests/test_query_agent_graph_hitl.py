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


class EmptyRetriever:
    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
    ):
        return []


class InteractivePlanner:
    """第一次缺Context，第二次读取用户补充后READY。"""

    def plan(
        self,
        *,
        question: str,
        semantic_context: str,
        query_context,
    ):
        session_context = (
            query_context
            .session_context
        )

        if not session_context:
            return PlanningClarification(
                clarification_question=(
                    "请确认科技贷款"
                    "还是绿色贷款。"
                ),

                missing_context=(
                    "贷款业务主题",
                ),

                reason=(
                    "当前存在多个"
                    "合理业务主题。"
                ),
            )

        assert (
            "绿色贷款"
            in session_context[-1]
        )

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


def test_graph_interrupts_and_resumes():
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
            InteractivePlanner()
        ),

        sql_generator=(
            FakeSQLGenerator()
        ),

        validation_workflow=(
            PassingValidationWorkflow()
        ),

        semantic_validator=None,

        max_semantic_retries=1,

        max_clarification_rounds=3,
    )

    thread_id = (
        "hitl-test-thread"
    )

    # ========================================================
    # First invocation -> interrupt
    # ========================================================

    first = graph.start(
        thread_id=thread_id,

        question=(
            "统计本期贷款余额"
        ),
    )

    assert "__interrupt__" in first

    interrupts = first[
        "__interrupt__"
    ]

    assert len(
        interrupts
    ) == 1

    payload = (
        interrupts[0].value
    )

    assert (
        payload["question"]
        == (
            "请确认科技贷款"
            "还是绿色贷款。"
        )
    )

    assert (
        "generated_sql"
        not in first
    )

    # ========================================================
    # Resume with human context
    # ========================================================

    second = graph.resume(
        thread_id=thread_id,

        answer=(
            "这次统计绿色贷款。"
        ),
    )

    # Graph应该继续完成，
    # 而不是再次从头创建一个新任务。

    assert (
        "__interrupt__"
        not in second
    )

    assert second[
        "query_plan"
    ].tables == (
        "dwd_hd_201_cldwdk",
    )

    assert second[
        "query_plan"
    ].metrics == (
        "green_loan_balance",
    )

    assert (
        second[
            "session_context"
        ]
        == (
            "User clarification: "
            "这次统计绿色贷款。",
        )
    )

    assert (
        second[
            "clarification_round"
        ]
        == 1
    )

    assert (
        second[
            "candidate_sql"
        ]
        is not None
    )

    assert (
        second["success"]
        is True
    )

    assert (
        second[
            "trusted_sql"
        ]
        is not None
    )