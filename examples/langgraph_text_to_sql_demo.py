from __future__ import annotations

import uuid

from pathlib import Path

from langgraph.types import (
    Interrupt,
)

from sql_pilot_engine.app.factory import (
    build_workflow,
)
from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)
from sql_pilot_engine.context.embedding import (
    TokenHashEmbeddingProvider,
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
from sql_pilot_engine.context.semantic.loan_domain import (
    LOAN_DOMAIN_CONTEXT_DOCUMENTS,
)
from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)
from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)
from sql_pilot_engine.llm.deepseek_client import (
    DeepSeekLLMClient,
)
from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticSQLValidator,
)


def build_graph() -> QueryAgentGraph:
    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    semantic_model_path = (
        project_root
        / "sql_pilot_engine"
        / "context"
        / "semantic"
        / "loan_model.json"
    )

    semantic_model = (
        SemanticModelLoader().load(
            semantic_model_path
        )
    )

    embedding_provider = (
        TokenHashEmbeddingProvider(
            dimensions=128
        )
    )

    vector_store = QdrantVectorStore(
        embedding_provider=(
            embedding_provider
        ),

        collection_name=(
            "langgraph_text_to_sql_demo"
        ),
    )

    vector_store.add(
        LOAN_DOMAIN_CONTEXT_DOCUMENTS
    )

    model = (
        DeepSeekLLMClient.from_env()
    )

    return QueryAgentGraph(
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
                model=model
            )
        ),

        sql_generator=(
            SQLGenerator(
                model=model
            )
        ),

        validation_workflow=(
            build_workflow(
                max_retries=0
            )
        ),

        semantic_validator=(
            SemanticSQLValidator(
                model=model
            )
        ),

        max_semantic_retries=1,

        max_clarification_rounds=3,
    )


def get_interrupt(
    result: dict,
):
    interrupts = result.get(
        "__interrupt__",
        ()
    )

    if not interrupts:
        return None

    return interrupts[0]


def main() -> None:
    graph = build_graph()

    thread_id = (
        uuid.uuid4().hex
    )

    question = input(
        "Question > "
    ).strip()

    result = graph.start(
        thread_id=thread_id,
        question=question,
    )

    # ========================================================
    # Human-in-the-loop
    # ========================================================

    while True:
        current_interrupt = (
            get_interrupt(
                result
            )
        )

        if current_interrupt is None:
            break

        payload = (
            current_interrupt.value
        )

        print()
        print(
            "[Agent needs clarification]"
        )

        print(
            payload.get(
                "question"
            )
        )

        missing = payload.get(
            "missing_context",
            (),
        )

        if missing:
            print()
            print(
                "Missing context:"
            )

            for item in missing:
                print(
                    f"- {item}"
                )

        reason = payload.get(
            "reason"
        )

        if reason:
            print()
            print(
                "Reason:"
            )
            print(
                reason
            )

        answer = input(
            "\nYour clarification > "
        ).strip()

        if not answer:
            print(
                "Task stopped."
            )
            return

        result = graph.resume(
            thread_id=thread_id,
            answer=answer,
        )

    # ========================================================
    # Final
    # ========================================================

    print()
    print("=" * 70)
    print(
        "Agent3.0 · LangGraph Result"
    )
    print("=" * 70)

    print(
        "success:",
        result.get(
            "success"
        ),
    )

    print(
        "query_plan:",
        result.get(
            "query_plan"
        ),
    )

    print()
    print(
        "generated_sql:"
    )
    print(
        result.get(
            "generated_sql"
        )
    )

    print()
    print(
        "validation_status:",
        result.get(
            "validation_status"
        ),
    )

    print(
        "semantic_validation_status:",
        result.get(
            "semantic_validation_status"
        ),
    )

    print()
    print(
        "trusted_sql:"
    )
    print(
        result.get(
            "trusted_sql"
        )
    )

    if result.get(
        "error_message"
    ):
        print()
        print(
            "error:"
        )
        print(
            result[
                "error_message"
            ]
        )


if __name__ == "__main__":
    main()