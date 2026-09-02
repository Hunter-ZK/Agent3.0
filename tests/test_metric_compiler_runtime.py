from __future__ import annotations

# 这一组测试只验证 Phase 4.1 的 Runtime 接线与状态语义：
# Compiler 能否把结果写回 State、Graph Router 如何选择下一跳、
# Clarification 后是否彻底清理上一轮 SQL Candidate 状态。
#
# 它不验证 MetricSQLCompiler 自身的 SQL 生成正确性；那部分由
# tests/test_metric_compiler.py 单独覆盖。这样可以避免一个测试同时承担
# “编译算法”和“Runtime 编排”两个职责，定位失败时更清楚。
from sql_pilot_engine.generation.models import (
    CompilationEvidence,
    CompilationFallbackReason,
    GeneratedSQL,
    GenerationSource,
    MetricCompilationOutcome,
    QueryPlan,
)
from sql_pilot_engine.linking.models import (
    LinkedSchema,
)
from sql_pilot_engine.runtime.query_nodes import (
    QueryRuntimeNodes,
)


class SilentEventBus:
    """Runtime Node 单测使用的无副作用 EventBus。"""

    def publish(
        self,
        event,
    ) -> None:
        _ = event


class CompilingStageService:
    """
    固定返回 COMPILED 的最小 StageService Stub。

    这里故意不调用真实 Compiler，因为本测试只关心：
    QueryRuntimeNodes 收到 COMPILED Outcome 后，是否正确写入
    generated_sql / generation_source / generation_attempt，并路由到 Trust。
    """

    def try_compile_sql(
        self,
        *,
        plan,
        linked_schema,
        dialect,
    ):
        _ = plan
        _ = linked_schema

        return MetricCompilationOutcome.compiled(
            generated_sql=GeneratedSQL(
                sql="SELECT 1",
                dialect=dialect,
            ),
            evidence=CompilationEvidence(
                metric_names=("metric_a",),
                physical_table="table_a",
                metric_expressions=(
                    "SUM(value)",
                ),
            ),
        )


class FallbackStageService:
    """
    固定返回 NOT_COMPILABLE 的最小 StageService Stub。

    “无法确定性编译”是正常能力边界，不是 Runtime Error。
    Runtime 应把它路由到已有 LLM Generator，而不是把整个任务结束掉。
    """

    def try_compile_sql(
        self,
        *,
        plan,
        linked_schema,
        dialect,
    ):
        _ = plan
        _ = linked_schema
        _ = dialect

        return MetricCompilationOutcome.fallback(
            fallback_reason=(
                CompilationFallbackReason
                .COMPLEX_EXPRESSION
            ),
            reason="complex metric",
        )


def _state():
    """构造 Compiler Node 所需的最小合法 Runtime State。"""

    return {
        "thread_id": "test",
        "turn_id": "turn",
        "query_plan": QueryPlan(
            tables=("table_a",),
            dimensions=(),
            metrics=("metric_a",),
        ),
        # Node 单测中的 Stub 不读取 LinkedSchema 内容，因此这里只需要一个对象实例。
        "linked_schema": LinkedSchema(
            tables=()
        ),
        "dialect": "maxcompute",
        "generation_attempt": 0,
    }


def test_compiled_sql_routes_directly_to_trust():
    """
    Compiler 成功后不应再调用 LLM Generator，而应直接进入 Trust。

    同时 generation_attempt 必须 +1，因为它统计的是“产生过多少个 SQL Candidate”，
    不是“调用过多少次 LLM”。这个计数会影响后续 Semantic Retry 的上限判断。
    """

    nodes = QueryRuntimeNodes(
        stage_service=CompilingStageService(),
        event_bus=SilentEventBus(),
    )

    updates = nodes.compile_sql(
        _state()
    )

    combined = {
        **_state(),
        **updates,
    }

    assert (
        updates["generation_source"]
        == GenerationSource.COMPILED.value
    )
    assert updates["generation_attempt"] == 1
    assert (
        nodes.route_after_compilation(
            combined
        )
        == "trust"
    )


def test_not_compilable_routes_to_llm_generator():
    """
    NOT_COMPILABLE 必须被解释为“走 LLM fallback”，而不是任务失败。

    此时还没有新的 SQL Candidate，所以 generated_sql 与 generation_source
    都必须为空；真正进入 generate_sql Node 后才会写入 LLM 来源。
    """

    nodes = QueryRuntimeNodes(
        stage_service=FallbackStageService(),
        event_bus=SilentEventBus(),
    )

    updates = nodes.compile_sql(
        _state()
    )

    combined = {
        **_state(),
        **updates,
    }

    assert updates["generated_sql"] is None
    assert updates["generation_source"] is None
    assert (
        nodes.route_after_compilation(
            combined
        )
        == "generate"
    )


def test_validation_clarification_helper_matches_runtime_call_site():
    """
    防止 Clarification Helper 再次出现“调用名和定义名不一致”。

    生产 Runtime 调用 `_build_validation_clarification`，因此这个测试直接以
    同一个私有方法名执行。若有人把定义改回无下划线版本，测试会立即失败，
    而不是等线上真正出现 context_required 时才暴露 AttributeError。
    """

    question = (
        QueryRuntimeNodes
        ._build_validation_clarification(
            ("统计月份",)
        )
    )

    assert "统计月份" in question


def test_clarification_resume_clears_previous_sql_candidate_state(
    monkeypatch,
):
    """
    用户补充信息后，下一轮必须从 Context/Planning 重新计算请求级事实。

    上一轮的 QueryPlan、LinkedSchema、CompilationEvidence、Generated SQL、
    Trust Candidate 和 Semantic 状态都不能继续残留，否则新问题上下文可能
    与旧 SQL Candidate 混用，形成非常隐蔽的“状态穿越”错误。
    """

    # LangGraph interrupt 在真实运行中会暂停并等待 Command(resume=...)。
    # Node 单测不需要真正启动 Graph，所以把 interrupt 替换成固定用户回答。
    monkeypatch.setattr(
        "sql_pilot_engine.runtime.query_nodes.interrupt",
        lambda payload: "2026年7月",
    )

    nodes = QueryRuntimeNodes(
        # request_clarification 不会调用 StageService，因此这里使用最小占位对象即可。
        stage_service=object(),
        event_bus=SilentEventBus(),
    )

    state = {
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "clarification_question": "请确认统计月份",
        "missing_context": ("统计月份",),
        "clarification_reason": "time context required",
        "clarification_round": 0,
        "max_clarification_rounds": 3,
        "session_context": (),
        # 以下字段模拟上一轮已经走到 Compiler / Trust / Semantic 后留下的状态。
        "query_context": object(),
        "query_plan": object(),
        "linked_schema": object(),
        "linking_failures": (object(),),
        "linking_error_message": "old linking error",
        "compilation_status": "compiled",
        "compilation_fallback_reason": "old fallback",
        "compilation_evidence": object(),
        "generation_source": "compiled",
        "generated_sql": "SELECT old_sql",
        "revision_feedback": ("old feedback",),
        "generation_attempt": 1,
        "validation_status": "no_issue",
        "validation_error_message": "old validation error",
        "validation_issues": ({"rule_id": "OLD"},),
        "candidate_sql": "SELECT old_candidate",
        "semantic_validation_status": "fail",
        "semantic_missing_requirements": ("old",),
        "semantic_issues": ("old issue",),
        "trusted_sql": "SELECT old_trusted",
        "success": False,
        "error_message": None,
    }

    updates = nodes.request_clarification(
        state
    )

    # 用户回答被追加到 session_context，供下一轮 Context Builder / Planner 使用。
    assert updates["session_context"] == (
        "User clarification: 2026年7月",
    )
    assert updates["clarification_round"] == 1

    # 从 Planning 开始重新计算的所有请求级中间事实都必须清空。
    for key in (
        "query_context",
        "query_plan",
        "linked_schema",
        "compilation_status",
        "compilation_fallback_reason",
        "compilation_evidence",
        "generation_source",
        "generated_sql",
        "validation_status",
        "validation_error_message",
        "candidate_sql",
        "semantic_validation_status",
        "trusted_sql",
    ):
        assert updates[key] is None

    assert updates["linking_failures"] == ()
    assert updates["validation_issues"] == ()
    assert updates["semantic_missing_requirements"] == ()
    assert updates["semantic_issues"] == ()
    assert updates["revision_feedback"] == ()
    assert updates["generation_attempt"] == 0