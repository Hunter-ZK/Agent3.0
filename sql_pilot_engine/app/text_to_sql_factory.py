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
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticSQLValidator,
)
from sql_pilot_engine.services.text_to_sql_service import (
    TextToSQLService,
)


def build_text_to_sql_service(
    *,
    semantic_model_path: str | Path,
    context_documents: Iterable[ContextDocument],
    planner_model: TextGenerationModel,
    sql_model: TextGenerationModel,
    semantic_validator_model: (TextGenerationModel | None) = None,
    collection_name: str = ("agent3_text_to_sql"),
    embedding_dimensions: int = 128,
    max_sql_retries: int = 0,
    max_semantic_retries: int = 1,
) -> TextToSQLService:
    """构建完整Text-to-SQL产品服务。

    Composition Root只负责对象组装。

    调用者负责决定：
    - 使用哪个LLM；
    - 使用哪个Semantic Model；
    - 注入哪些Context Documents；
    - 是否启用Semantic Validation。

    这样Demo、Evaluation以及后续API入口
    可以共享完全相同的产品调用链。
    """
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
        
    # ========================================================
    # Embedding
    # ========================================================
    
    embedding_provider = (
        TokenHashEmbeddingProvider(
            dimensions=(
                embedding_dimensions
            ),
        )
    )
    
    # ========================================================
    # Vector Store
    # ========================================================
    
    vector_store = QdrantVectorStore(
        embedding_provider=(
            embedding_provider
        ),
        collection_name=collection_name,
    )
    
    vector_store.add(
        tuple(context_documents)
    )
    
    # ========================================================
    # Semantic Model
    # ========================================================
    
    semantic_model = (
        SemanticModelLoader().load(
            Path(
                semantic_model_path
            )
        )
    )
    
    # ========================================================
    # Optional Semantic Validator
    # ========================================================
    
    semantic_validator = None
    
    if (
        semantic_validator_model is not None
    ):
        semantic_validator = (
            SemanticSQLValidator(
                model=(
                    semantic_validator_model
                )
            )
        )

    # ========================================================
    # Service Composition
    # ========================================================
    
    return TextToSQLService(
        semantic_model=(
            semantic_model
        ),
        
        knowledge_retriever=(
            KnowledgeRetriever(
                vector_store
            )
        ),
        
        verified_sql_retriever=(
            VerifiedSQLRetriever(
                vector_store
            )
        ),
        
        context_builder=(
            QueryContextBuilder()
        ),
        
        planner=(
            QueryPlanner(
                model=planner_model
            )
        ),
        
        sql_generator=(
            SQLGenerator(
                model=sql_model
            )
        ),
        
        semantic_validator=(
            semantic_validator
        ),
        
        validation_workflow=(
            build_workflow(
                max_retries=(
                    max_sql_retries
                )
            )
        ),
        
        max_semantic_retries=(
            max_semantic_retries
        ),
    )