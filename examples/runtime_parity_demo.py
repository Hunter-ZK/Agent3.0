from __future__ import annotations

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
from sql_pilot_engine.evaluation.golden_cases import (
    TEXT_TO_SQL_GOLDEN_V0_1,
)
from sql_pilot_engine.evaluation.runtime_parity import (
    RuntimeParityRunner,
)
from sql_pilot_engine.evaluation.text_to_sql_evaluator import (
    TextToSQLEvaluator,
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
from sql_pilot_engine.services.text_to_sql_service import (
    TextToSQLService,
)


def build_runtimes():
    """
    用同一套底层依赖构建：

    1. Python Runtime
    2. LangGraph Runtime

    这样Parity主要比较 orchestration，
    而不是比较两套不同配置。
    """

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
        SemanticModelLoader()
        .load(
            semantic_model_path
        )
    )

    embedding_provider = (
        TokenHashEmbeddingProvider(
            dimensions=128
        )
    )

    vector_store = (
        QdrantVectorStore(
            embedding_provider=(
                embedding_provider
            ),
            collection_name=(
                "runtime_parity_demo"
            ),
        )
    )

    vector_store.add(
        LOAN_DOMAIN_CONTEXT_DOCUMENTS
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

    model = (
        DeepSeekLLMClient.from_env()
    )

    planner = QueryPlanner(
        model=model
    )

    sql_generator = SQLGenerator(
        model=model
    )

    semantic_validator = (
        SemanticSQLValidator(
            model=model
        )
    )

    # 两个Runtime分别持有自己的Workflow。
    # 避免未来Workflow出现状态后相互污染。
    python_workflow = (
        build_workflow(
            max_retries=0
        )
    )

    graph_workflow = (
        build_workflow(
            max_retries=0
        )
    )

    python_service = (
        TextToSQLService(
            semantic_model=(
                semantic_model
            ),
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
                python_workflow
            ),
            semantic_validator=(
                semantic_validator
            ),
            max_semantic_retries=1,
        )
    )

    graph = QueryAgentGraph(
        semantic_model=(
            semantic_model
        ),
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
            graph_workflow
        ),
        semantic_validator=(
            semantic_validator
        ),
        max_semantic_retries=1,
        max_clarification_rounds=3,
    )

    return (
        python_service,
        graph,
    )


def main() -> None:
    (
        python_service,
        graph,
    ) = build_runtimes()

    runner = RuntimeParityRunner(
        python_service=(
            python_service
        ),
        langgraph=graph,
        evaluator=(
            TextToSQLEvaluator()
        ),
    )

    report = runner.run(
        TEXT_TO_SQL_GOLDEN_V0_1
    )

    print()
    print("=" * 76)
    print(
        "Agent3.0 Runtime Parity V0.1"
    )
    print("=" * 76)

    for result in report.results:
        print()
        print(
            f"[{result.case_id}]"
        )

        print(
            "Python behavior:",
            result
            .python_evaluation
            .actual_behavior
            .value,
        )

        print(
            "Graph behavior:",
            result
            .langgraph_evaluation
            .actual_behavior
            .value,
        )

        print(
            "Python golden:",
            result
            .python_evaluation
            .passed,
        )

        print(
            "Graph golden:",
            result
            .langgraph_evaluation
            .passed,
        )

        print(
            "Behavior equal:",
            result.behavior_equal,
        )

        if (
            result.tables_equal
            is not None
        ):
            print(
                "Tables equal:",
                result.tables_equal,
            )
            print(
                "Dimensions equal:",
                result.dimensions_equal,
            )
            print(
                "Metrics equal:",
                result.metrics_equal,
            )
            print(
                "Filters equal:",
                result.filters_equal,
            )
            print(
                "GroupBy equal:",
                result.group_by_equal,
            )
            print(
                "Pipeline equal:",
                result.pipeline_equal,
            )
            print(
                "Trusted SQL equal:",
                result.trusted_sql_equal,
            )

        print(
            "PARITY:",
            (
                "PASS"
                if result.parity_passed
                else "FAIL"
            ),
        )

        python_error = (
            result
            .python_evaluation
            .error_message
        )

        graph_error = (
            result
            .langgraph_evaluation
            .error_message
        )

        if python_error:
            print(
                "Python error:",
                python_error,
            )

        if graph_error:
            print(
                "Graph error:",
                graph_error,
            )

    print()
    print("=" * 76)
    print("Summary")
    print("=" * 76)

    print(
        "Cases:",
        report.total_cases,
    )

    print(
        "Parity:",
        (
            f"{report.passed_cases}"
            f"/{report.total_cases}"
        ),
    )

    print(
        "Parity rate:",
        f"{report.parity_rate:.1%}",
    )

    print(
        "Python golden pass:",
        f"{report.python_pass_rate:.1%}",
    )

    print(
        "LangGraph golden pass:",
        f"{report.langgraph_pass_rate:.1%}",
    )


if __name__ == "__main__":
    main()