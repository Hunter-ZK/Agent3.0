from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sql_pilot_engine.app.factory import (
    build_workflow,
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

from sql_pilot_engine.generation.llm import (
    TextGenerationModel,
)

from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)

from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)

from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)

from sql_pilot_engine.runtime.checkpoint_memory import (
    MemoryCheckpointStore,
)

from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)

from sql_pilot_engine.services.semantic_validation_service import (
    SemanticSQLValidator,
)

from sql_pilot_engine.services.text_to_sql_service import (
    TextToSQLService,
)


def build_text_to_sql_service(
    *,
    semantic_model_path: str | Path,

    context_documents: Iterable[
        ContextDocument
    ],

    planner_model: TextGenerationModel,

    sql_model: TextGenerationModel,

    semantic_validator_model: (
        TextGenerationModel | None
    ) = None,

    checkpoint_store: (
        CheckpointStore | None
    ) = None,

    collection_name: str = (
        "agent3_text_to_sql"
    ),

    embedding_dimensions: int = 128,

    max_sql_retries: int = 0,

    max_semantic_retries: int = 1,

    max_clarification_rounds: int = 3,
) -> TextToSQLService:
    """
    Text-to-SQL Composition Root。

    这个函数只负责：
    创建组件
    → 组装 QueryAgentGraph
    → 用 TextToSQLService 包装 Application API

    不执行任何业务流程。
    """

    # ========================================================
    # Config Validation
    # ========================================================

    if embedding_dimensions <= 0:
        raise ValueError(
            "embedding_dimensions "
            "must be greater than 0"
        )

    if max_sql_retries < 0:
        raise ValueError(
            "max_sql_retries "
            "must be >= 0"
        )

    if max_semantic_retries < 0:
        raise ValueError(
            "max_semantic_retries "
            "must be >= 0"
        )

    if max_clarification_rounds <= 0:
        raise ValueError(
            "max_clarification_rounds "
            "must be greater than 0"
        )

    # ========================================================
    # Context Infrastructure
    # ========================================================

    embedding_provider = (
        TokenHashEmbeddingProvider(
            dimensions=(
                embedding_dimensions
            ),
        )
    )

    vector_store = QdrantVectorStore(
        embedding_provider=(
            embedding_provider
        ),

        collection_name=(
            collection_name
        ),
    )

    vector_store.add(
        tuple(
            context_documents
        )
    )

    knowledge_retriever = (
        KnowledgeRetriever(
            vector_store
        )
    )

    verified_sql_retriever = (
        VerifiedSQLRetriever(
            vector_store
        )
    )

    context_builder = (
        QueryContextBuilder()
    )

    # ========================================================
    # Semantic Model
    # ========================================================

    semantic_model = (
        SemanticModelLoader()
        .load(
            Path(
                semantic_model_path
            )
        )
    )

    # ========================================================
    # Planning / Generation
    # ========================================================

    planner = QueryPlanner(
        model=planner_model
    )

    sql_generator = SQLGenerator(
        model=sql_model
    )

    # ========================================================
    # Validation
    # ========================================================

    semantic_validator = None

    if (
        semantic_validator_model
        is not None
    ):
        semantic_validator = (
            SemanticSQLValidator(
                model=(
                    semantic_validator_model
                )
            )
        )

    validation_workflow = (
        build_workflow(
            max_retries=(
                max_sql_retries
            )
        )
    )

    # ========================================================
    # Runtime
    # ========================================================

    runtime_checkpoint_store = (
        checkpoint_store
        if checkpoint_store is not None
        else MemoryCheckpointStore()
    )

    graph = QueryAgentGraph(
        semantic_model=semantic_model,

        knowledge_retriever=(
            knowledge_retriever
        ),

        verified_sql_retriever=(
            verified_sql_retriever
        ),

        context_builder=(
            context_builder
        ),

        planner=planner,

        sql_generator=(
            sql_generator
        ),

        validation_workflow=(
            validation_workflow
        ),

        checkpoint_store=(
            runtime_checkpoint_store
        ),

        semantic_validator=(
            semantic_validator
        ),

        max_semantic_retries=(
            max_semantic_retries
        ),

        max_clarification_rounds=(
            max_clarification_rounds
        ),
    )

    # ========================================================
    # Application Facade
    # ========================================================

    return TextToSQLService(
        graph=graph
    )