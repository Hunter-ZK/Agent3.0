from __future__ import annotations

from sql_pilot_engine.context.builder import QueryContextBuilder
from sql_pilot_engine.context.semantic.models import (
    SemanticColumn,
    SemanticModel,
    SemanticTable,
)
from sql_pilot_engine.generation.models import PlanningClarification
from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)
from sql_pilot_engine.runtime.query_graph import QueryAgentGraph
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLRequest,
)
from sql_pilot_engine.capabilities.text_to_sql import (
    TextToSQLCapability,
)


class EmptyRetriever:
    def retrieve(self, *, question: str, top_k: int):
        return []


class NeedClarificationPlanner:
    def plan(self, *, query_context) -> PlanningClarification:
        return PlanningClarification(
            clarification_question="请说明同比和环比的时间口径。",
            missing_context=(
                "同比时间口径",
                "环比时间口径",
            ),
            reason="当前上下文不足以可靠生成SQL。",
        )


class ShouldNotGenerateSQL:
    def generate(self, **kwargs):
        raise AssertionError(
            "SQLGenerator must not be called "
            "when clarification is required."
        )


class ShouldNotValidateWorkflow:
    def run(self, sql: str):
        raise AssertionError(
            "Validation workflow must not be called "
            "when clarification is required."
        )


def build_test_semantic_model() -> SemanticModel:
    return SemanticModel(
        tables=(
            SemanticTable(
                name="dwd_hd_101_cldwdk",
                description="科技贷款明细宽表",
                columns=(
                    SemanticColumn(
                        name="loan_bal_rmb",
                        description="贷款余额",
                        data_type="DECIMAL(22,2)",
                    ),
                    SemanticColumn(
                        name="dt",
                        description="统计日期",
                        data_type="STRING",
                    ),
                ),
            ),
        ),
        metrics=(),
    )


def test_clarification_stops_sql_generation():
    graph = QueryAgentGraph(
        semantic_model=build_test_semantic_model(),
        knowledge_retriever=EmptyRetriever(),
        verified_sql_retriever=EmptyRetriever(),
        context_builder=QueryContextBuilder(),
        planner=NeedClarificationPlanner(),
        sql_generator=ShouldNotGenerateSQL(),
        validation_workflow=ShouldNotValidateWorkflow(),
        checkpoint_store=MemoryCheckpointStore(),
        semantic_validator=None,
        max_semantic_retries=1,
    )

    service = TextToSQLCapability(
        graph=graph,
    )

    response = service.generate(
        TextToSQLRequest(
            question="统计高新技术企业的贷款余额同比及环比情况"
        )
    )

    assert isinstance(response, TextToSQLClarification)
    assert response.thread_id
    assert (
        response.clarification_question
        == "请说明同比和环比的时间口径。"
    )
    assert response.missing_context == (
        "同比时间口径",
        "环比时间口径",
    )
    assert response.reason == "当前上下文不足以可靠生成SQL。"
