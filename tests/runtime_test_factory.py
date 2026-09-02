from __future__ import annotations

from typing import Any

from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)
from sql_pilot_engine.context.semantic.models import (
    SemanticModel,
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

    Runtime 测试不验证 RAG 检索质量，
    因此默认返回空结果。
    """

    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
    ):
        _ = question
        _ = top_k

        return []


class NullEventBus:
    """
    Runtime 测试默认事件出口。

    EventBus 自身行为由
    test_runtime_event_bus.py
    独立验证。
    """

    def publish(
        self,
        event: RuntimeEvent,
    ) -> None:
        _ = event


def build_runtime_graph(
    *,
    semantic_model: SemanticModel,
    planner: Any,
    schema_linker: Any,
    sql_generator: Any,
    trusted_sql_workflow: Any,
    semantic_validator: Any | None = None,
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

    测试应该模拟生产 Object Graph：

    Fake Components
        ↓
    TextToSQLStageService
        ↓
    QueryRuntimeNodes
        ↓
    QueryAgentGraph

    不允许 Runtime 测试继续使用
    QueryAgentGraph 的历史 constructor。
    """

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

    stage_service = (
        TextToSQLStageService(
            semantic_model=(
                semantic_model
            ),
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
            schema_linker=(
                schema_linker
            ),
            sql_generator=(
                sql_generator
            ),
            trusted_sql_workflow=(
                trusted_sql_workflow
            ),
            semantic_validator=(
                semantic_validator
            ),
            knowledge_top_k=(
                knowledge_top_k
            ),
            verified_sql_top_k=(
                verified_sql_top_k
            ),
        )
    )

    nodes = (
        QueryRuntimeNodes(
            stage_service=(
                stage_service
            ),
            event_bus=(
                active_event_bus
            ),
            max_semantic_retries=(
                max_semantic_retries
            ),
            max_clarification_rounds=(
                max_clarification_rounds
            ),
        )
    )

    return (
        QueryAgentGraph(
            nodes=nodes,
            checkpoint_store=(
                active_checkpoint_store
            ),
        )
    )