from __future__ import annotations

from typing import Any

from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)
from sql_pilot_engine.context.semantic.models import (
    SemanticModel,
)
from sql_pilot_engine.generation.models import (
    CompilationFallbackReason,
    MetricCompilationOutcome,
)
from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)
from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)
from sql_pilot_engine.runtime.event import (
    RuntimeEvent,
)
from sql_pilot_engine.runtime.event_bus import (
    EventBus,
)
from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)
from sql_pilot_engine.runtime.query_nodes import (
    QueryRuntimeNodes,
)
from sql_pilot_engine.services.text_to_sql_stage_service import (
    TextToSQLStageService,
)


class EmptyRetriever:
    """
    Runtime 单测默认使用的空 Retriever。

    【为什么测试里需要这个 Fake】
    Runtime 测试的目标是验证 Graph / Node / StageService 的协作关系，
    而不是验证 RAG 检索质量。如果这里接真实 VectorStore，测试结果会受到
    embedding、索引内容和外部基础设施影响，反而无法稳定定位 Runtime 问题。

    因此这个对象只满足 KnowledgeRetriever / VerifiedSQLRetriever 在测试对象图中
    所需的最小行为：接收 question、top_k，然后返回空结果。
    """

    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
    ):
        # 显式消费参数，表示 Fake 的接口与生产 Retriever 保持一致，
        # 只是当前测试不关心参数值。
        _ = question
        _ = top_k

        return []


class NullEventBus:
    """
    Runtime 单测默认事件出口。

    Runtime Event 是旁路可观测能力，不应该决定 Text-to-SQL 主链是否成功。
    EventBus 自身的发布/收集行为已经由 test_runtime_event_bus.py 独立验证，
    因此普通 Runtime 测试使用无副作用 Sink，避免把两个测试目标耦合在一起。
    """

    def publish(
        self,
        event: RuntimeEvent,
    ) -> None:
        _ = event


class FallbackMetricCompiler:
    """
    Runtime 公共测试默认使用的“强制 LLM fallback” Compiler Stub。

    【为什么公共 Runtime Factory 不默认使用真实 MetricSQLCompiler】
    Runtime 测试通常在验证 Graph 路由、clarification、retry、Trust 或 Semantic Validation，
    它们不应该因为某个测试 SemanticModel 恰好新增了 aggregation/source_column，突然从
    “LLM 路径”切换到“Compiler 路径”，从而改变原测试的核心意图。

    因此公共 Factory 默认让 Compiler 返回一个正常 NOT_COMPILABLE：
        compile_sql -> generate_sql(LLM)

    这不是绕开新架构，因为：
    - TextToSQLStageService 仍然完整注入 metric_compiler Contract；
    - Graph 仍然真实经过 compile_sql Node；
    - 只是测试用策略实现固定选择 fallback 分支；
    - Compiler 的真实 AST/指标编译能力由 test_metric_compiler.py 独立验证；
    - Compiler Runtime 成功分支由 test_metric_compiler_runtime.py 独立验证。

    如果某个集成测试明确需要真实 Compiler，只需通过 build_runtime_graph(metric_compiler=...)
    显式注入，不需要修改公共 Factory。
    """

    def compile(
        self,
        *,
        plan,
        linked_schema,
        dialect: str,
    ) -> MetricCompilationOutcome:
        _ = plan
        _ = linked_schema
        _ = dialect

        return MetricCompilationOutcome.fallback(
            fallback_reason=(
                CompilationFallbackReason.COMPLEX_EXPRESSION
            ),
            reason=(
                "runtime test default: force the LLM generation path"
            ),
        )


def build_runtime_graph(
    *,
    semantic_model: SemanticModel,
    planner: Any,
    schema_linker: Any,
    sql_generator: Any,
    trusted_sql_workflow: Any,
    semantic_validator: Any | None = None,
    metric_compiler: Any | None = None,
    knowledge_retriever: Any | None = None,
    verified_sql_retriever: Any | None = None,
    context_builder: QueryContextBuilder | None = None,
    checkpoint_store: CheckpointStore | None = None,
    event_bus: EventBus | None = None,
    knowledge_top_k: int = 5,
    verified_sql_top_k: int = 3,
    max_semantic_retries: int = 1,
    max_clarification_rounds: int = 3,
) -> QueryAgentGraph:
    """
    Runtime 测试统一 Composition Root。

    【为什么测试也必须有 Composition Root】
    生产代码当前真实对象图是：

        SemanticModel
            ├──> SchemaLinker
            └──> MetricSQLCompiler

        Retriever / Planner / Linker / Compiler / Generator / Trust / SemanticValidator
                                    ↓
                           TextToSQLStageService
                                    ↓
                           QueryRuntimeNodes
                                    ↓
                            QueryAgentGraph

    Runtime 测试必须复制这张“依赖拓扑”，但允许把具体实现替换成 Fake / Stub。
    这里的重点是 Contract 和调用链必须与生产一致，而不是所有测试都必须运行真实算法。

    Phase 4.1 新增 MetricSQLCompiler 后，TextToSQLStageService 的构造函数已经要求
    metric_compiler。这里必须同步注入，否则测试 Composition Root 已经落后于生产 Contract。

    默认使用 FallbackMetricCompiler 是为了保持旧 Runtime 测试的关注点稳定；需要测试真实
    Compiler 时由调用方显式传入 metric_compiler。这样“测试编排”和“测试编译算法”不会混在一起。
    """

    # 以下依赖允许调用方覆盖；没有显式传入时使用最小、无外部副作用的默认实现。
    active_knowledge_retriever = (
        knowledge_retriever
        if knowledge_retriever is not None
        else EmptyRetriever()
    )

    active_verified_sql_retriever = (
        verified_sql_retriever
        if verified_sql_retriever is not None
        else EmptyRetriever()
    )

    active_context_builder = (
        context_builder
        if context_builder is not None
        else QueryContextBuilder()
    )

    active_checkpoint_store = (
        checkpoint_store
        if checkpoint_store is not None
        else MemoryCheckpointStore()
    )

    active_event_bus = (
        event_bus
        if event_bus is not None
        else NullEventBus()
    )

    active_metric_compiler = (
        metric_compiler
        if metric_compiler is not None
        else FallbackMetricCompiler()
    )

    stage_service = TextToSQLStageService(
        semantic_model=semantic_model,
        knowledge_retriever=(
            active_knowledge_retriever
        ),
        verified_sql_retriever=(
            active_verified_sql_retriever
        ),
        context_builder=(
            active_context_builder
        ),
        planner=planner,
        schema_linker=schema_linker,
        metric_compiler=active_metric_compiler,
        sql_generator=sql_generator,
        trusted_sql_workflow=(
            trusted_sql_workflow
        ),
        semantic_validator=(
            semantic_validator
        ),
        knowledge_top_k=knowledge_top_k,
        verified_sql_top_k=(
            verified_sql_top_k
        ),
    )

    # Node Adapter 只拿已经组装好的 StageService 与 Runtime 横切依赖。
    nodes = QueryRuntimeNodes(
        stage_service=stage_service,
        event_bus=active_event_bus,
        max_semantic_retries=(
            max_semantic_retries
        ),
        max_clarification_rounds=(
            max_clarification_rounds
        ),
    )

    # Graph 不重新拿 Planner / Generator / Compiler 等业务依赖；
    # 它只拿 Nodes 与 Checkpoint，保持“Graph = orchestration”的冻结边界。
    return QueryAgentGraph(
        nodes=nodes,
        checkpoint_store=(
            active_checkpoint_store
        ),
    )