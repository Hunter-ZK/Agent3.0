from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.builder import QueryContextBuilder
from sql_pilot_engine.context.semantic.models import (
    SemanticColumn,
    SemanticModel,
    SemanticTable,
)
from sql_pilot_engine.generation.models import QueryPlan
from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)
from sql_pilot_engine.runtime.query_graph import QueryAgentGraph
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticValidationResult,
    SemanticValidationStatus,
)


class EmptyRetriever:
    def retrieve(self, *, question: str, top_k: int):
        return []


class ReadyPlanner:
    def plan(self, *, query_context) -> QueryPlan:
        return QueryPlan(
            tables=("dwd_hd_201_cldwdk",),
            dimensions=(),
            metrics=("green_loan_balance",),
            filters=("dt = '${p_month_yyyymm}'",),
            group_by=(),
        )


@dataclass(frozen=True)
class FakeGeneratedSQL:
    sql: str


class RecordingSQLGenerator:
    def __init__(self) -> None:
        self.call_count = 0
        self.feedback_history: list[tuple[str, ...]] = []

    def generate(self, **kwargs):
        self.call_count += 1
        feedback = tuple(
            kwargs.get("revision_feedback", ())
        )
        self.feedback_history.append(feedback)

        return FakeGeneratedSQL(
            sql=(
                f"SELECT {self.call_count} AS attempt, "
                "SUM(loan_bal_rmb) AS loan_balance "
                "FROM dwd_hd_201_cldwdk "
                "WHERE dt = '${p_month_yyyymm}'"
            )
        )


@dataclass(frozen=True)
class FakeValidationResult:
    success: bool
    final_status: str
    fix_response: object | None = None


class PassingValidationWorkflow:
    def run(self, sql: str):
        return FakeValidationResult(
            success=True,
            final_status="no_issue",
        )


class FailingValidationWorkflow:
    def run(self, sql: str):
        return FakeValidationResult(
            success=False,
            final_status="blocked",
        )


class SequenceSemanticValidator:
    def __init__(
        self,
        results: tuple[SemanticValidationResult, ...],
    ) -> None:
        self._results = list(results)
        self.call_count = 0

    def validate(self, **kwargs) -> SemanticValidationResult:
        if not self._results:
            raise AssertionError(
                "Semantic validator received more calls than expected."
            )
        self.call_count += 1
        return self._results.pop(0)


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
    generator,
    semantic_validator,
    validation_workflow=None,
    max_semantic_retries: int = 1,
) -> QueryAgentGraph:
    return QueryAgentGraph(
        semantic_model=build_semantic_model(),
        knowledge_retriever=EmptyRetriever(),
        verified_sql_retriever=EmptyRetriever(),
        context_builder=QueryContextBuilder(),
        planner=ReadyPlanner(),
        sql_generator=generator,
        validation_workflow=(
            validation_workflow
            or PassingValidationWorkflow()
        ),
        checkpoint_store=MemoryCheckpointStore(),
        semantic_validator=semantic_validator,
        max_semantic_retries=max_semantic_retries,
        max_clarification_rounds=3,
    )


def test_semantic_pass_produces_trusted_sql():
    generator = RecordingSQLGenerator()
    validator = SequenceSemanticValidator(
        (
            SemanticValidationResult(
                status=SemanticValidationStatus.PASS,
            ),
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=validator,
    )

    state = graph.start(
        thread_id="semantic-pass",
        question="统计本期绿色贷款余额",
    )

    assert state["success"] is True
    assert state["trusted_sql"] is not None
    assert validator.call_count == 1
    assert generator.call_count == 1


def test_semantic_fail_retries_then_passes():
    generator = RecordingSQLGenerator()
    validator = SequenceSemanticValidator(
        (
            SemanticValidationResult(
                status=SemanticValidationStatus.FAIL,
                issues=("缺少必要业务条件",),
            ),
            SemanticValidationResult(
                status=SemanticValidationStatus.PASS,
            ),
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=validator,
        max_semantic_retries=1,
    )

    state = graph.start(
        thread_id="semantic-retry",
        question="统计本期绿色贷款余额",
    )

    assert state["success"] is True
    assert state["trusted_sql"] is not None
    assert generator.call_count == 2
    assert validator.call_count == 2
    assert generator.feedback_history[1]


def test_deterministic_block_stops_before_semantic_validation():
    generator = RecordingSQLGenerator()
    validator = SequenceSemanticValidator(
        (
            SemanticValidationResult(
                status=SemanticValidationStatus.PASS,
            ),
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=validator,
        validation_workflow=FailingValidationWorkflow(),
    )

    state = graph.start(
        thread_id="deterministic-block",
        question="统计本期绿色贷款余额",
    )

    assert state["success"] is False
    assert state["trusted_sql"] is None
    assert validator.call_count == 0


def test_semantic_need_clarification_interrupts():
    generator = RecordingSQLGenerator()
    validator = SequenceSemanticValidator(
        (
            SemanticValidationResult(
                status=SemanticValidationStatus.NEED_CLARIFICATION,
                missing_requirements=("业务时间口径",),
            ),
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=validator,
    )

    state = graph.start(
        thread_id="semantic-clarification",
        question="统计贷款余额同比",
    )

    assert "__interrupt__" in state
    payload = state["__interrupt__"][0].value
    assert "业务时间口径" in payload["question"]
