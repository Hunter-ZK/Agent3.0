from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from sql_pilot_engine.capabilities.text_to_sql import (
    TextToSQLCapability,
)
from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)
from sql_pilot_engine.context.embedding import (
    TokenHashEmbeddingProvider,
)
from sql_pilot_engine.context.models import (
    ContextDocument,
)
from sql_pilot_engine.context.qdrant_store import (
    QdrantVectorStore,
)
from sql_pilot_engine.context.retriever import (
    KnowledgeRetriever,
    VerifiedSQLRetriever,
)
from sql_pilot_engine.context.semantic.loader import (
    SemanticModelLoader,
)
from sql_pilot_engine.generation.metric_compiler import (
    MetricSQLCompiler,
)
from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)
from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)
from sql_pilot_engine.linking.schema_linker import (
    SchemaLinker,
)
from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
    TextGenerationModel,
)
from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)
from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)
from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)
from sql_pilot_engine.runtime.event_bus import (
    DevEventSink,
    EventBus,
)
from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)
from sql_pilot_engine.runtime.query_nodes import (
    QueryRuntimeNodes,
)
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticSQLValidator,
)
from sql_pilot_engine.services.text_to_sql_stage_service import (
    TextToSQLStageService,
)
from sql_pilot_engine.workflow.protocols import (
    TrustedSQLWorkflowPort,
)


def build_text_to_sql_capability(
    *,
    semantic_model_path: str | Path,
    context_documents: Iterable[
        ContextDocument
    ],
    planner_model: TextGenerationModel,
    sql_model: TextGenerationModel,
    metadata_provider_factory: Callable[
        [],
        MetadataProvider,
    ],
    trusted_sql_workflow: TrustedSQLWorkflowPort,
    context_builder: QueryContextBuilder | None = None,
    semantic_validator_model: StructuredGenerationModel | None = None,
    checkpoint_store: CheckpointStore | None = None,
    event_bus: EventBus | None = None,
    collection_name: str = "agent3_text_to_sql",
    embedding_dimensions: int = 128,
    knowledge_top_k: int = 5,
    verified_sql_top_k: int = 3,
    max_semantic_retries: int = 1,
    max_clarification_rounds: int = 3,
) -> TextToSQLCapability:
    """
    Text-to-SQL 的 Composition Root（依赖组装入口）。

    【为什么 Phase 4.1 必须修改 Factory】
    MetricSQLCompiler 是新的长期依赖，它需要 SemanticModel，但它不应该：
    - 在 Runtime Node 中自己读取文件；
    - 在 StageService 中临时 new；
    - 在 Graph 中持有业务依赖。

    因此只能在 Composition Root 完成实例化，再注入 StageService。这保持了既定边界：

        外部配置 / 基础设施
            ↓
        build_text_to_sql_capability              <- 本函数
            ↓
        SemanticModel ─────┬──> SchemaLinker
                           ├──> MetricSQLCompiler
                           └──> TextToSQLStageService / TrustEvidence

        Planner + Linker + Compiler + Generator + Trust + SemanticValidator
            ↓
        TextToSQLStageService
            ↓
        QueryRuntimeNodes
            ↓
        QueryAgentGraph
            ↓
        TextToSQLCapability

    这条顺序不是代码排版偏好，而是依赖方向决定的：只有先创建长期依赖，才能再组装
    StageService；只有 StageService 完成后才能创建 Runtime Nodes；Graph 又只依赖 Nodes，
    最后 Application Facade 只依赖 Graph。

    SQL Core / MetadataProvider / TrustedSQLWorkflow 仍由调用方提前组装后注入，本函数不把
    SQL Core 的 Composition 重新吞回 Text-to-SQL 子系统。
    """

    # ========================================================
    # 1. Config Validation
    # ========================================================
    # 在创建任何外部资源前先验证纯配置，避免已经初始化 Qdrant/Checkpoint 后才发现参数非法。

    if embedding_dimensions <= 0:
        raise ValueError(
            "embedding_dimensions must be greater than 0"
        )

    if max_semantic_retries < 0:
        raise ValueError(
            "max_semantic_retries must be >= 0"
        )

    if max_clarification_rounds <= 0:
        raise ValueError(
            "max_clarification_rounds must be greater than 0"
        )

    # ========================================================
    # 2. Context Infrastructure
    # ========================================================
    # Knowledge 与 Verified SQL 当前共用同一个 VectorStore，但通过不同 Retriever 暴露语义。
    # Composition Root 可以决定它们共享基础设施，业务 Stage 不需要知道底层存储细节。

    embedding_provider = TokenHashEmbeddingProvider(
        dimensions=embedding_dimensions,
    )

    vector_store = QdrantVectorStore(
        embedding_provider=embedding_provider,
        collection_name=collection_name,
    )

    # context_documents 可能是一次性 iterable，因此在这里一次性物化后交给 store。
    vector_store.add(
        tuple(context_documents)
    )

    knowledge_retriever = KnowledgeRetriever(
        vector_store
    )
    verified_sql_retriever = VerifiedSQLRetriever(
        vector_store
    )

    active_context_builder = (
        context_builder
        if context_builder is not None
        else QueryContextBuilder()
    )

    # ========================================================
    # 3. Semantic Model
    # ========================================================
    # SemanticModel 是长期批准资产，在 capability 构建时加载一次。
    # 本阶段只消费它，不在这里做资产盘点、自动纠错或重新命名。

    semantic_model = SemanticModelLoader().load(
        Path(semantic_model_path)
    )

    # ========================================================
    # 4. Planning / Physical Linking / Generation
    # ========================================================

    planner = QueryPlanner(
        model=planner_model
    )

    # SchemaLinker 必须先于 Compiler 工作，因为 Compiler 只能消费已经确认的物理绑定。
    # metadata_provider_factory 保留 factory 形式，使调用方继续控制 Provider 生命周期/实现。
    schema_linker = SchemaLinker(
        metadata_provider=metadata_provider_factory(),
        semantic_model=semantic_model,
    )

    # Compiler 与 SchemaLinker 必须共享同一 SemanticModel 实例。
    # 如果各自重新加载，运行中就可能出现“Linker 看到 A 版本、Compiler 看到 B 版本”的漂移。
    metric_compiler = MetricSQLCompiler(
        semantic_model=semantic_model,
    )

    # SQLGenerator 仍是通用 LLM fallback 与 semantic retry 的生成器，Compiler 不替代它。
    sql_generator = SQLGenerator(
        model=sql_model
    )

    # ========================================================
    # 5. Optional Semantic Validation
    # ========================================================

    semantic_validator = None
    if semantic_validator_model is not None:
        semantic_validator = SemanticSQLValidator(
            model=semantic_validator_model
        )

    # ========================================================
    # 6. Runtime Infrastructure
    # ========================================================
    # 调用方可注入生产实现；未提供时使用进程内开发默认实现。

    runtime_checkpoint_store = (
        checkpoint_store
        if checkpoint_store is not None
        else MemoryCheckpointStore()
    )

    runtime_event_bus = (
        event_bus
        if event_bus is not None
        else DevEventSink()
    )

    # ========================================================
    # 7. Stage Service
    # ========================================================
    # 这是业务能力第一次汇合的位置：Service 拥有各 Stage 依赖，但仍不持有 Graph/Checkpoint。

    stage_service = TextToSQLStageService(
        semantic_model=semantic_model,
        knowledge_retriever=knowledge_retriever,
        verified_sql_retriever=verified_sql_retriever,
        context_builder=active_context_builder,
        planner=planner,
        schema_linker=schema_linker,
        metric_compiler=metric_compiler,
        sql_generator=sql_generator,
        trusted_sql_workflow=trusted_sql_workflow,
        semantic_validator=semantic_validator,
        knowledge_top_k=knowledge_top_k,
        verified_sql_top_k=verified_sql_top_k,
    )

    # ========================================================
    # 8. Runtime Nodes -> Graph -> Application Facade
    # ========================================================
    # Nodes 适配 State/路由，Graph 只声明拓扑，Capability 最终提供稳定应用 API。

    runtime_nodes = QueryRuntimeNodes(
        stage_service=stage_service,
        event_bus=runtime_event_bus,
        max_semantic_retries=max_semantic_retries,
        max_clarification_rounds=max_clarification_rounds,
    )

    graph = QueryAgentGraph(
        nodes=runtime_nodes,
        checkpoint_store=runtime_checkpoint_store,
    )

    return TextToSQLCapability(
        graph=graph
    )