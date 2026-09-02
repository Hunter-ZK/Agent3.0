from __future__ import annotations


from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from sql_pilot_engine.runtime.state import (
    QueryAgentState,
)

from langgraph.types import (
    Command,
)

from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)

from sql_pilot_engine.runtime.query_nodes import (
    QueryRuntimeNodes,
)

class QueryAgentGraph:
    """Agent3.0 Text-to-SQL LangGraph Runtime V0.1.

    Graph只负责编排。

    业务能力继续复用现有：
    - Context Retriever
    - QueryPlanner
    - SQLGenerator
    - TrustedSQLWorkflow
    - SemanticSQLValidator
    """
    
    def __init__(
        self,
        *,
        nodes: QueryRuntimeNodes,
        checkpoint_store: CheckpointStore,
    ) -> None:

        
        self.checkpointer = (
            checkpoint_store.get_backend()
        )

        self.nodes = nodes

        self.graph = self._build_graph()


    # ========================================================
    # Graph Definition
    # ========================================================
    def _build_graph(self):

        builder = StateGraph(
            QueryAgentState
        )

        builder.add_node(
            "retrieve_context",
            self.nodes.retrieve_context,
        )

        builder.add_node(
            "plan_query",
            self.nodes.plan_query,
        )

        builder.add_node(
            "link_schema",
            self.nodes.link_schema,
        )
        
        builder.add_node(
            "compile_sql",
            self.nodes.compile_sql,
        )

        builder.add_node(
            "generate_sql",
            self.nodes.generate_sql,
        )

        builder.add_node(
            "trust_sql",
            self.nodes.trust_sql,
        )
        
        builder.add_node(
            "semantic_validate",
            self.nodes.semantic_validate,
        )
        
        builder.add_node(
            "request_clarification",
            self.nodes.request_clarification,
        )


        # ----------------------------------------------------
        # Main path
        # ----------------------------------------------------
        builder.add_edge(
            START,
            "retrieve_context",
        )

        builder.add_edge(
            "retrieve_context",
            "plan_query",
        )
        
        # ----------------------------------------------------
        # Planning routing
        # ----------------------------------------------------
        builder.add_conditional_edges(
            "plan_query",
            self.nodes.route_after_plan,
            {
                "link": "link_schema",
                "clarify": (
                    "request_clarification"
                ),
                "end": END,
            },
        )
        
        
        builder.add_conditional_edges(
            "link_schema",

            self.nodes
            .route_after_linking,

            {
                "compile": (
                    "compile_sql"
                ),

                "end": END,
            },
        )
        
        builder.add_conditional_edges(
            "compile_sql",

            self.nodes
            .route_after_compilation,

            {
                "trust": "trust_sql",

                "generate": (
                    "generate_sql"
                ),
            },
        )

        builder.add_edge(
            "generate_sql",
            "trust_sql",
        )
        
        # ----------------------------------------------------
        # Deterministic Validation routing
        # ----------------------------------------------------

        builder.add_conditional_edges(
            "trust_sql",
            self.nodes.route_after_trust,
            {
                "semantic_validate": (
                    "semantic_validate"
                ),

                "clarify": (
                    "request_clarification"
                ),

                "end": END,
            }
        )
        
        # ----------------------------------------------------
        # Semantic Validation routing
        # ----------------------------------------------------
        
        builder.add_conditional_edges(
            "semantic_validate",
            self.nodes.route_after_semantic_validation,
            {
                "retry": "generate_sql",
                "clarify": (
                    "request_clarification"
                ),
                "end": END,
            },
        )
        
        builder.add_conditional_edges(
            "request_clarification",
            self.nodes.route_after_clarification,
            {
                "continue":(
                    "retrieve_context"
                ),
                "end": END,
            },
        )

        return builder.compile(
            checkpointer=(
                self.checkpointer
            )
        )


    def start(
        self,
        *,
        thread_id: str,
        question: str,
        dialect: str = "maxcompute",
        session_context: (
            tuple[str, ...]
        ) = (),
    ) -> dict:

        normalized_thread_id = (
            thread_id.strip()
        )

        normalized_question = (
            question.strip()
        )

        if not normalized_thread_id:
            raise ValueError(
                "thread_id cannot be empty"
            )

        if not normalized_question:
            raise ValueError(
                "question cannot be empty"
            )

        config = {
            "configurable": {
                "thread_id": (
                    normalized_thread_id
                )
            }
        }

        initial_state = (
            self.nodes.build_initial_state(
                thread_id=(
                    normalized_thread_id
                ),
                question=(
                    normalized_question
                ),
                dialect=dialect,
                session_context=(
                    session_context
                ),
            )
        )

        return self.graph.invoke(
            initial_state,
            config=config,
        )
        
    def resume(
        self,
        *,
        thread_id: str,
        answer: str,
    ) -> dict:
        
        if not thread_id.strip():
            raise ValueError(
                "thread_id cannot be empty"
            )
            
        if not answer.strip():
            raise ValueError(
                "answer cannot be empty"
            )
            
        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }
        
        return self.graph.invoke(
        Command(
            resume=answer
        ),

        config=config,
    )