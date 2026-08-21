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
from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticValidationResult,
    SemanticValidationStatus,
)


# ============================================================
# Retriever
# ============================================================


class EmptyRetriever:
    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
    ):
        return []


# ============================================================
# Planner
# ============================================================


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


# ============================================================
# Generator
# ============================================================


@dataclass(
    frozen=True,
)
class FakeGeneratedSQL:
    sql: str


class RecordingSQLGenerator:
    """
    记录每次生成时收到的 revision_feedback。

    这样测试不仅能证明 Graph 确实发生了 Retry，
    还可以证明 Semantic Validator 的反馈
    真正传回了下一次 Generator。
    """

    def __init__(self) -> None:
        self.call_count = 0

        self.feedback_history: list[
            tuple[str, ...]
        ] = []

    def generate(
        self,
        **kwargs,
    ):
        self.call_count += 1

        feedback = tuple(
            kwargs.get(
                "revision_feedback",
                (),
            )
        )

        self.feedback_history.append(
            feedback
        )

        return FakeGeneratedSQL(
            sql=(
                "SELECT "
                f"{self.call_count} AS attempt, "
                "SUM(loan_bal_rmb) "
                "AS loan_balance "
                "FROM dwd_hd_201_cldwdk "
                "WHERE "
                "dt = '${p_month_yyyymm}'"
            )
        )


# ============================================================
# Deterministic Validation
# ============================================================


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


class FailingValidationWorkflow:
    def run(
        self,
        sql: str,
    ):
        return FakeValidationResult(
            success=False,
            final_status="blocked",
        )


# ============================================================
# Semantic Validator
# ============================================================


class SequenceSemanticValidator:
    """
    按顺序返回预设 Semantic Validation 结果。

    用于稳定模拟：

    FAIL -> PASS

    NEED_CLARIFICATION
        -> FAIL
        -> PASS

    等 Runtime 控制流。
    """

    def __init__(
        self,
        results: tuple[
            SemanticValidationResult,
            ...,
        ],
    ) -> None:
        self._results = list(results)
        self.call_count = 0

    def validate(
        self,
        **kwargs,
    ) -> SemanticValidationResult:
        if not self._results:
            raise AssertionError(
                "Semantic validator received "
                "more calls than expected."
            )

        self.call_count += 1

        return self._results.pop(0)


# ============================================================
# Fixtures
# ============================================================


def build_semantic_model() -> SemanticModel:
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


def build_graph(
    *,
    generator,
    semantic_validator,
    validation_workflow=None,
    max_semantic_retries: int = 1,
) -> QueryAgentGraph:
    return QueryAgentGraph(
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

        sql_generator=generator,

        validation_workflow=(
            validation_workflow
            or PassingValidationWorkflow()
        ),

        semantic_validator=(
            semantic_validator
        ),

        max_semantic_retries=(
            max_semantic_retries
        ),

        max_clarification_rounds=3,
    )


# ============================================================
# Test 1
# Semantic PASS
# ============================================================


def test_semantic_pass_produces_trusted_sql():
    generator = (
        RecordingSQLGenerator()
    )

    semantic_validator = (
        SequenceSemanticValidator(
            (
                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .PASS
                    ),
                ),
            )
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=(
            semantic_validator
        ),
    )

    state = graph.start(
        thread_id=(
            "semantic-pass-thread"
        ),
        question=(
            "统计本期绿色贷款余额"
        ),
    )

    assert (
        generator.call_count
        == 1
    )

    assert (
        semantic_validator.call_count
        == 1
    )

    assert (
        state["generation_attempt"]
        == 1
    )

    assert (
        state[
            "semantic_validation_status"
        ]
        == "pass"
    )

    assert (
        state["success"]
        is True
    )

    assert (
        state["trusted_sql"]
        == state["candidate_sql"]
    )


# ============================================================
# Test 2
# Semantic FAIL -> Retry -> PASS
# ============================================================


def test_semantic_fail_retries_and_then_passes():
    generator = (
        RecordingSQLGenerator()
    )

    semantic_validator = (
        SequenceSemanticValidator(
            (
                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .FAIL
                    ),
                    missing_requirements=(
                        "同比",
                    ),
                    issues=(
                        "SQL未实现同比计算",
                    ),
                ),

                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .PASS
                    ),
                ),
            )
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=(
            semantic_validator
        ),
        max_semantic_retries=1,
    )

    state = graph.start(
        thread_id=(
            "semantic-retry-thread"
        ),
        question=(
            "统计本期绿色贷款余额同比"
        ),
    )

    assert (
        generator.call_count
        == 2
    )

    assert (
        semantic_validator.call_count
        == 2
    )

    assert (
        state["generation_attempt"]
        == 2
    )

    # 第一次生成没有修订意见。
    assert (
        generator
        .feedback_history[0]
        == ()
    )

    # 第二次生成必须收到
    # Semantic Validator 的反馈。
    assert (
        "Missing requirement: 同比"
        in generator
        .feedback_history[1]
    )

    assert (
        "Semantic issue: "
        "SQL未实现同比计算"
        in generator
        .feedback_history[1]
    )

    assert (
        state[
            "semantic_validation_status"
        ]
        == "pass"
    )

    assert (
        state["revision_feedback"]
        == ()
    )

    assert (
        state["success"]
        is True
    )

    assert (
        state["trusted_sql"]
        is not None
    )


# ============================================================
# Test 3
# Semantic Retry Exhaustion
# ============================================================


def test_semantic_retry_stops_after_limit():
    generator = (
        RecordingSQLGenerator()
    )

    semantic_validator = (
        SequenceSemanticValidator(
            (
                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .FAIL
                    ),
                    missing_requirements=(
                        "同比",
                    ),
                ),

                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .FAIL
                    ),
                    missing_requirements=(
                        "同比",
                    ),
                ),
            )
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=(
            semantic_validator
        ),
        max_semantic_retries=1,
    )

    state = graph.start(
        thread_id=(
            "semantic-exhaust-thread"
        ),
        question=(
            "统计本期绿色贷款余额同比"
        ),
    )

    # 首次生成 + 1次Retry
    assert (
        generator.call_count
        == 2
    )

    assert (
        state["generation_attempt"]
        == 2
    )

    assert (
        state[
            "semantic_validation_status"
        ]
        == "fail"
    )

    assert (
        state["success"]
        is False
    )

    assert (
        state["trusted_sql"]
        is None
    )


# ============================================================
# Test 4
# Semantic Clarification
# must start a NEW retry lifecycle
# ============================================================


def test_semantic_clarification_resets_retry_budget():
    generator = (
        RecordingSQLGenerator()
    )

    semantic_validator = (
        SequenceSemanticValidator(
            (
                # 第一次：
                # Context不足，需要询问用户。
                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .NEED_CLARIFICATION
                    ),
                    missing_requirements=(
                        "贷款业务主题",
                    ),
                ),

                # 用户补充Context以后，
                # 新一轮首次SQL仍然有语义问题。
                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .FAIL
                    ),
                    missing_requirements=(
                        "同比",
                    ),
                ),

                # 应该还允许一次Retry。
                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .PASS
                    ),
                ),
            )
        )
    )

    graph = build_graph(
        generator=generator,
        semantic_validator=(
            semantic_validator
        ),
        max_semantic_retries=1,
    )

    thread_id = (
        "semantic-clarify-thread"
    )

    first = graph.start(
        thread_id=thread_id,
        question=(
            "统计本期贷款余额同比"
        ),
    )

    assert "__interrupt__" in first

    assert (
        first["generation_attempt"]
        == 1
    )

    payload = (
        first[
            "__interrupt__"
        ][0].value
    )

    assert (
        payload["type"]
        == "clarification"
    )

    assert (
        "贷款业务主题"
        in payload["question"]
    )

    second = graph.resume(
        thread_id=thread_id,
        answer=(
            "这次统计绿色贷款。"
        ),
    )

    # 整个任务一共调用了三次Generator：
    #
    # 1. clarification之前
    # 2. 用户补充Context后的首次生成
    # 3. Semantic FAIL后的Retry
    assert (
        generator.call_count
        == 3
    )

    assert (
        semantic_validator.call_count
        == 3
    )

    # 关键断言：
    #
    # clarification之后Generation生命周期
    # 已重新开始，所以最终是attempt=2，
    # 而不是累计成attempt=3。
    assert (
        second["generation_attempt"]
        == 2
    )

    assert (
        generator
        .feedback_history[0]
        == ()
    )

    # 用户补充了Context，
    # 不能继续携带上一轮feedback。
    assert (
        generator
        .feedback_history[1]
        == ()
    )

    # 新Context下的第一次SQL FAIL，
    # 下一次才收到Semantic revision feedback。
    assert (
        "Missing requirement: 同比"
        in generator
        .feedback_history[2]
    )

    assert (
        second["success"]
        is True
    )

    assert (
        second["trusted_sql"]
        is not None
    )

    assert (
        second[
            "semantic_validation_status"
        ]
        == "pass"
    )


# ============================================================
# Test 5
# Deterministic Validation Failure
# ============================================================


def test_deterministic_validation_failure_has_final_failure_state():
    generator = (
        RecordingSQLGenerator()
    )

    # deterministic validation失败以后，
    # Semantic Validator根本不应该被调用。
    semantic_validator = (
        SequenceSemanticValidator(
            (
                SemanticValidationResult(
                    status=(
                        SemanticValidationStatus
                        .PASS
                    ),
                ),
            )
        )
    )

    graph = build_graph(
        generator=generator,

        semantic_validator=(
            semantic_validator
        ),

        validation_workflow=(
            FailingValidationWorkflow()
        ),
    )

    state = graph.start(
        thread_id=(
            "deterministic-fail-thread"
        ),
        question=(
            "统计本期绿色贷款余额"
        ),
    )

    assert (
        generator.call_count
        == 1
    )

    assert (
        semantic_validator.call_count
        == 0
    )

    assert (
        state["candidate_sql"]
        is None
    )

    assert (
        state["success"]
        is False
    )

    assert (
        state["trusted_sql"]
        is None
    )