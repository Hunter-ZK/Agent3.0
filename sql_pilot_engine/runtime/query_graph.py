from __future__ import annotations

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)

from sql_pilot_engine.context.retriever import (
    KnowledgeRetriever,
    VerifiedSQLRetriever,
)

from sql_pilot_engine.context.semantic.models import (
    SemanticModel,
)

from sql_pilot_engine.context.semantic.renderer import (
    SemanticModelRenderer,
)

from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)

from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)

from sql_pilot_engine.runtime.state import (
    QueryAgentState,
)

from sql_pilot_engine.runtime.validation import (
    SQLValidationPort,
)


class QueryAgentGraph:

    def __init__(
        self,
        *,
        semantic_model: SemanticModel,
        knowledge_retriever:(
            KnowledgeRetriever
        ),
        verified_sql_retriever: (
            VerifiedSQLRetriever
        ),
        context_builder: QueryContextBuilder,
        planner: QueryPlanner,
        sql_generator: SQLGenerator,
        validator: SQLValidationPort,
    ) -> None:

        self.semantic_model = (
            semantic_model
        )

        self.knowledge_retriever = (
            knowledge_retriever
        )

        self.verified_sql_retriever = (
            verified_sql_retriever
        )

        self.context_builder = (
            context_builder
        )

        self.planner = planner
        self.sql_generator = sql_generator
        self.validator = validator

        self.semantic_renderer = (
            SemanticModelRenderer()
        )

        self.graph = self._build_graph()


    def _build_graph(self):

        builder = StateGraph(
            QueryAgentState
        )

        builder.add_node(
            "retrieve_context",
            self._retrieve_context,
        )

        builder.add_node(
            "plan_query",
            self._plan_query,
        )

        builder.add_node(
            "generate_sql",
            self._generate_sql,
        )

        builder.add_node(
            "validate_sql",
            self._validate_sql,
        )

        builder.add_edge(
            START,
            "retrieve_context",
        )

        builder.add_edge(
            "retrieve_context",
            "plan_query",
        )

        builder.add_edge(
            "plan_query",
            "generate_sql",
        )

        builder.add_edge(
            "generate_sql",
            "validate_sql",
        )

        builder.add_edge(
            "validate_sql",
            END,
        )

        return builder.compile()


    def _retrieve_context(
            self,
            state: QueryAgentState,
    ) -> dict:

        question = state["question"]

        business_knowledge = (
            self.knowledge_retriever.retrieve(
                question=question,
                top_k=5,
            )
        )

        verified_sql = (
            self.verified_sql_retriever.retrieve(
                question=question,
                top_k=3,
            )
        )

        query_context = (
            self.context_builder.build(
                question=question,
                business_knowledge=(
                    business_knowledge
                ),
                verified_sql=(
                    verified_sql
                ),
            )
        )

        semantic_context = (
            self.semantic_renderer.render(
                self.semantic_model
            )
        )

        return {
            "query_context":(
                query_context
            ),
            "semantic_context":(
                semantic_context
            ),
        }

    def _plan_query(
        self,
        state: QueryAgentState,
    ) -> dict:

        dialect = state.get(
            "dialect",
            "maxcompute",
        )

        result = (
            self.sql_generator.generate(
                question=state["question"],
                plan=state["query_plan"],
                semantic_context=state["semantic_context"],
                query_context=state["query_context"],
                dialect=dialect,
            )
        )

        return {
            "generated_sql":(
                result.sql
            )
        }


    def _validate_sql(
        self,       
        state: QueryAgentState,
    ) -> dict:

        dialect = state.get("dialect","maxcompute")

        result = self.validator.validate(
            sql=state["generated_sql"],
            dialect=dialect,
        )

        return {
            "trusted_sql":(
                result.final_sql
            ),
            "validation_status":(
                result.status
            ),
            "success": (
                result.accepted
            ),
        }

    