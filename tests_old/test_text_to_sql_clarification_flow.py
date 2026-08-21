from __future__ import annotations

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
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLRequest,
)
from sql_pilot_engine.services.text_to_sql_service import (
    TextToSQLService,
)


# ============================================================
# Fake Retriever
# ============================================================


class EmptyRetriever:
    """测试专用 Retriever。

    本测试不关心 RAG 检索内容，
    所以始终返回空结果。
    """

    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
    ):
        return []


# ============================================================
# Fake Planner
# ============================================================


class NeedClarificationPlanner:
    """模拟 Planner 判断 Context 不足。

    关键点：
    Planner 不返回 QueryPlan，
    而是返回 PlanningClarification。
    """

    def plan(
        self,
        *,
        question: str,
        semantic_context: str,
        query_context,
    ) -> PlanningClarification:

        return PlanningClarification(
            clarification_question=(
                "请说明同比和环比的时间口径。"
            ),
            missing_context=(
                "同比时间口径",
                "环比时间口径",
            ),
            reason=(
                "当前上下文不足以可靠生成SQL。"
            ),
        )


# ============================================================
# Fake SQL Generator
# ============================================================


class ShouldNotGenerateSQL:
    """如果 Clarification 后仍调用 Generator，
    测试必须立即失败。
    """

    def generate(
        self,
        **kwargs,
    ):
        raise AssertionError(
            "SQLGenerator must not be called "
            "when clarification is required."
        )


# ============================================================
# Fake Validation Workflow
# ============================================================


class ShouldNotValidateWorkflow:
    """如果连 SQL 都不应该生成，
    Validation 更不应该执行。
    """

    def run(
        self,
        sql: str,
    ):
        raise AssertionError(
            "Validation workflow must not be called "
            "when clarification is required."
        )


# ============================================================
# Semantic Model
# ============================================================


def build_test_semantic_model() -> SemanticModel:
    """构造最小可用 Semantic Model。

    TextToSQLService 内部会真正调用
    SemanticModelRenderer，因此这里不能简单传 None。
    """

    table = SemanticTable(
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
    )

    return SemanticModel(
        tables=(table,),
        metrics=(),
    )


# ============================================================
# Test
# ============================================================


def test_clarification_stops_sql_generation():
    """Planner要求澄清时：

    1. Service 应返回 TextToSQLClarification；
    2. SQL Generator 不允许执行；
    3. Validation Workflow 不允许执行。
    """

    service = TextToSQLService(
        semantic_model=(
            build_test_semantic_model()
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
            NeedClarificationPlanner()
        ),

        sql_generator=(
            ShouldNotGenerateSQL()
        ),

        semantic_validator=None,

        validation_workflow=(
            ShouldNotValidateWorkflow()
        ),

        max_semantic_retries=1,
    )

    response = service.generate(
        TextToSQLRequest(
            question=(
                "统计高新技术企业的"
                "贷款余额同比及环比情况"
            )
        )
    )

    assert isinstance(
        response,
        TextToSQLClarification,
    )

    assert (
        response.clarification_question
        == "请说明同比和环比的时间口径。"
    )

    assert response.missing_context == (
        "同比时间口径",
        "环比时间口径",
    )

    assert (
        response.reason
        == "当前上下文不足以可靠生成SQL。"
    )