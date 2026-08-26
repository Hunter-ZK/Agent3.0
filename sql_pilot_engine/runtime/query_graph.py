from __future__ import annotations

from uuid import uuid4

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
from sql_pilot_engine.generation.models import (
    PlanningClarification,
)
from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)

from sql_pilot_engine.runtime.state import (
    QueryAgentState,
)

from sql_pilot_engine.services.semantic_validation_service import (
    SemanticSQLValidator,
    SemanticValidationResult,
    SemanticValidationStatus,
)

from sql_pilot_engine.workflow.protocols import (
    TrustedSQLWorkflowPort,
)

from langgraph.types import (
    Command,
    interrupt,
)

from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)

from sql_pilot_engine.linking.schema_linker import (
    SchemaLinker,
    SchemaLinkingError,
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
        semantic_model: SemanticModel,
        knowledge_retriever:(
            KnowledgeRetriever
        ),
        verified_sql_retriever: (
            VerifiedSQLRetriever
        ),
        context_builder: QueryContextBuilder,
        planner: QueryPlanner,
        schema_linker: SchemaLinker,
        sql_generator: SQLGenerator,
        trusted_sql_workflow: (
            TrustedSQLWorkflowPort
        ),
        checkpoint_store: CheckpointStore,
        semantic_validator: (
            SemanticSQLValidator | None
        ) = None,
        max_semantic_retries: int = 1,
        max_clarification_rounds: int = 3,
    ) -> None:

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
        self.schema_linker = schema_linker
        self.sql_generator = sql_generator
        self.trusted_sql_workflow = trusted_sql_workflow
        
        self.semantic_validator = (
            semantic_validator
        )
        
        self.max_semantic_retries = (
            max_semantic_retries
        )
        
        self.max_clarification_rounds = (
            max_clarification_rounds
        )
        
        self.checkpointer = (
            checkpoint_store.get_backend()
        )

        self.semantic_renderer = (
            SemanticModelRenderer()
        )

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
            self._retrieve_context,
        )

        builder.add_node(
            "plan_query",
            self._plan_query,
        )

        builder.add_node(
            "link_schema",
            self._link_schema,
        )

        builder.add_node(
            "generate_sql",
            self._generate_sql,
        )

        builder.add_node(
            "trust_sql",
            self._trust_sql,
        )
        
        builder.add_node(
            "semantic_validate",
            self._semantic_validate,
        )
        
        builder.add_node(
            "request_clarification",
            self._request_clarification,
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
            self._route_after_plan,
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
            self._route_after_linking,
            {
                "generate": "generate_sql",
                "end": END,
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
            self._route_after_trust,
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
            self._route_after_semantic_validation,
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
            self._route_after_clarification,
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

    # ========================================================
    # Node 1
    # Context Intelligence
    # ========================================================
    
    def _retrieve_context(
            self,
            state: QueryAgentState,
    ) -> dict:

        question = state["question"]
        
        semantic_context = (
            self.semantic_renderer.render(
                self.semantic_model
            )
        )

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
                semantic_context=semantic_context,
                business_knowledge=(
                    business_knowledge
                ),
                verified_sql=(
                    verified_sql
                ),
                session_context=(
                    state.get(
                        "session_context",
                        (),
                    )
                ),
            )
        )

        return {
            "query_context":(
                query_context
            ),
        }


    # ========================================================
    # Node 2
    # Planning
    # ========================================================
    def _plan_query(
        self,
        state: QueryAgentState,
    ) -> dict:


        query_context = state.get("query_context")

        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing"
                "before planning."
            )
        
        outcome = self.planner.plan(
            query_context=(
                query_context
            ),
        )
        
        if isinstance(
            outcome,
            PlanningClarification,
        ):
            return {
                "clarification_question": (
                    outcome
                    .clarification_question
                ),

                "missing_context": (
                    outcome.missing_context
                ),

                "clarification_reason": (
                    outcome.reason
                ),

                "success": False,   
            }

        return {
            "query_plan": outcome,

            "clarification_question": None,

            "missing_context": (),

            "clarification_reason": "",

            "success": False,
            
            "linked_schema": None,
            "linking_error_message": None,
        }

    # ========================================================
    # Node 3
    # Schema Linking
    # ========================================================
    
    def _link_schema(
        self,
        state: QueryAgentState,
    ) -> dict:
        
        plan = state.get(
            "query_plan"
        )
        
        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing "
                "before schema linking."
            )

        try:
            linked_schema = (
                self.schema_linker.link(
                    plan=plan
                )
            )
        
        except SchemaLinkingError as error:
            
            message = str(error)
            
            return {
                "linked_schema": None,
                "linking_error_message": (
                    message
                ),
                "error_message": message,
                "success": False,
            }
            
        if not linked_schema.resolved:
            
            unresolved = ", ".join(
                linked_schema.unresolved_terms
                
            )

            return {
                "linked_schema": (
                    linked_schema
                ),

                "linking_error_message": (
                    message
                ),

                "error_message": message,

                "success": False,
            }

        return {
            "linked_schema": (
                linked_schema
            ),

            "linking_error_message": None,

            "error_message": None,
        }

    # ========================================================
    # Node 4
    # SQL Generation
    # ========================================================
    
    def _generate_sql(
        self,
        state: QueryAgentState,
    ) -> dict:
        attempt = (
            state.get(
                "generation_attempt",
                0
            )
            + 1
        )

        query_context = state.get(
            "query_context"
        )

        linked_schema = state.get(
            "linked_schema"
        )

        plan = state.get(
            "query_plan"
        )

        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing "
                "before SQL generation."
            )

        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing "
                "before SQL generation."
            )
            
        if linked_schema is None:
            raise RuntimeError(
                "LinkedSchema is missing "
                "before SQL generation."
            )
        
        result = (
            self.sql_generator.generate(
                plan=plan,
                linked_schema=linked_schema,
                query_context=query_context,
                dialect=state.get("dialect","maxcompute"),
                revision_feedback=state.get("revision_feedback",(),),
            )
        )
        
        return {
            "generated_sql":result.sql,
            "generation_attempt":attempt,
        }

    # ========================================================
    # Node 4
    # Trusted SQL Workflow
    # ========================================================

    def _trust_sql(
        self,
        state: QueryAgentState,
    ) -> dict:

        query_context = state.get(
            "query_context"
        )

        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing "
                "before Trusted SQL workflow."
            )

        generated_sql = state.get(
            "generated_sql"
        )

        if not generated_sql:
            raise RuntimeError(
                "Generated SQL is missing "
                "before Trusted SQL workflow."
            )

        trust_result = (
            self.trusted_sql_workflow.run(
                generated_sql,
                dialect=state.get(
                    "dialect",
                    "maxcompute",
                ),
                query_context=query_context,
            )
        )
        
        
        validation_missing_context = tuple(
            trust_result.missing_context
            or ()
        )

        if (
            trust_result.success
            and not trust_result.trusted_sql
        ):
            raise RuntimeError(
                "TrustedSQLWorkflow succeeded "
                "without trusted_sql."
            )

        updates = {
            # 暂时保留现有 public/state 字段名，
            # Phase 2 TrustLevel 重构时统一处理。
            "validation_status": (
                trust_result.final_status
            ),

            "validation_error_message": (
                trust_result.error_message
            ),

            "validation_missing_context": (
                validation_missing_context
            ),

            # 这里只表示：
            # SQL Trust Workflow 已接受，
            # 但仍等待 Semantic Validator
            # 判断是否真正满足 QueryPlan。
            "candidate_sql": (
                trust_result.trusted_sql
            ),

            "trusted_sql": None,

            "success": False,
        }
        
        if trust_result.final_status == "context_required":
            updates.update(
                {
                    "clarification_question": (
                        self
                        ._build_validation_clarification(
                            validation_missing_context
                        )
                    ),

                    "missing_context": (
                        validation_missing_context
                    ),

                    "clarification_reason": (
                        trust_result.error_message
                        or (
                            "Trusted SQL 审查发现"
                            "仍缺少必要业务上下文。"
                        )
                    ),
                }
            )
        else:
            updates.update(
                {
                    "missing_context": (),
                    "clarification_question": None,
                    "clarification_reason": "",
                }
            )
        
        return updates
    
    # ========================================================
    # Node 5
    # Semantic Validation
    # ========================================================
    

    def _semantic_validate(
        self,
        state: QueryAgentState,
    ) -> dict:
        
        if self.semantic_validator is None:
            return {
                "semantic_result": None,
                "semantic_validation_status": None,
                "trusted_sql":state.get("candidate_sql",""),
                "success":state.get("candidate_sql") is not None,
            }
            
        result = (
            self.semantic_validator.validate(
                sql=state["candidate_sql"],
                plan=state["query_plan"],
                query_context=state["query_context"],
            )
        )
        
        updates: dict = {
            "semantic_validation_status": (
                result.status.value
            ),

            "semantic_missing_requirements": (
                tuple(
                    result.missing_requirements
                )
            ),

            "semantic_issues": (
                tuple(
                    result.issues
                )
            ),
        }

        if result.passed:
            updates.update(
                {
                    "trusted_sql": (
                        state[
                            "candidate_sql"
                        ]
                    ),

                    "success": True,

                    "revision_feedback": (),
                }
            )

            return updates

        if (
            result.status
            is SemanticValidationStatus
            .NEED_CLARIFICATION
        ):
            updates.update(
                {
                    "trusted_sql": None,

                    "success": False,

                    "clarification_question": (
                        self
                        ._build_semantic_clarification(
                            result
                        )
                    ),

                    "missing_context": (
                        result
                        .missing_requirements
                    ),
                }
            )

            return updates

        updates.update(
            {
                "trusted_sql": None,

                "success": False,

                "revision_feedback": (
                    self
                    ._build_revision_feedback(
                        result
                    )
                ),
            }
        )

        return updates
        
    # ========================================================
    # Routing
    # ========================================================
    
    @staticmethod
    def _route_after_plan(
        state: QueryAgentState,
    ) -> str:

        if state.get(
            "error_message"
        ):
            return "end"

        if state.get(
            "clarification_question"
        ):
            return "clarify"

        return "link"

    @staticmethod
    def _route_after_linking(
        state: QueryAgentGraph,
    ) -> str:
        
        linked_schema = state.get(
            "linked_schema"
        )
        
        if state.get(
            "error_message"
        ):
            return "end"
        
        if linked_schema is None:
            return "end"
        
        if not linked_schema.resolved:
            return "end"
        
        return "generate"

    @staticmethod
    def _route_after_trust(
        state: QueryAgentState,
    ) -> str:

        if (
            state.get(
                "validation_status"
            )
            == "context_required"
        ):

            if not state.get(
                "missing_context"
            ):
                raise RuntimeError(
                    "Trusted SQL returned "
                    "context_required without "
                    "missing_context."
                )

            return "clarify"

        if (
            state.get(
                "candidate_sql"
            )
            is None
        ):
            return "end"

        return "semantic_validate"

    @staticmethod
    def _route_after_semantic_validation(
        state: QueryAgentState,
    ) -> str:

        status = state.get(
            "semantic_validation_status"
        )

        if status is None:
            return "end"

        if (
            status
            == SemanticValidationStatus.PASS.value
        ):
            return "end"

        if (
            status
            == (
                SemanticValidationStatus
                .NEED_CLARIFICATION
                .value
            )
        ):
            return "clarify"

        attempt = state.get(
            "generation_attempt",
            0,
        )

        max_retries = state.get(
            "max_semantic_retries",
            0,
        )

        if attempt <= max_retries:
            return "retry"

        return "end"

    @staticmethod
    def _route_after_clarification(
        state: QueryAgentState,
    ) -> str:

        if state.get(
            "error_message"
        ):
            return "end"

        return "continue"


    @staticmethod
    def _route_after_validation(
        state: QueryAgentState,
    ) -> str:

        if (
            state.get(
                "validation_status"
            )
            == "context_required"
            and state.get(
                "clarification_question"
            )
        ):
            return "clarify"

        if (
            state.get(
                "candidate_sql"
            )
            is None
        ):
            return "end"

        return "semantic_validate"

    # ========================================================
    # Helpers
    # ========================================================

    def _build_initial_state(
        self,
        *,
        thread_id: str,
        question: str,
        dialect: str,
        session_context: tuple[str, ...],
    ) -> QueryAgentState:
        """
        为一个新的 Turn 构建干净 State。

        同一个 thread_id 可以包含多个 Turn，
        因此 start() 必须显式清除上一 Turn
        留下的所有 request-scoped 中间状态。
        """

        return {
            # Runtime Identity
            "thread_id": thread_id,
            "turn_id": str(uuid4()),
            "event_type": None,

            # Input
            "question": question,
            "dialect": dialect,
            "session_context": (
                session_context
            ),

            # Context
            "query_context": None,

            # Planning
            "query_plan": None,
            "clarification_question": None,
            "missing_context": (),
            "clarification_reason": "",

            # HITL
            "clarification_round": 0,
            "max_clarification_rounds": (
                self.max_clarification_rounds
            ),
            
            # Linking
            "linked_schema": None,
            "linking_error_message": None,

            # Generation
            "generated_sql": None,
            "revision_feedback": (),
            "generation_attempt": 0,
            "max_semantic_retries": (
                self.max_semantic_retries
            ),

            "validation_status": None,
            "validation_error_message": None,

            "candidate_sql": None,
            "trusted_sql": None,

            "semantic_validation_status": None,
            "semantic_missing_requirements": (),
            "semantic_issues": (),

            # Final
            "trusted_sql": None,
            "success": False,
            "error_message": None,
        }


    @staticmethod
    def _build_revision_feedback(
        result: SemanticValidationResult,
    ) -> tuple[str, ...]:

        feedback: list[str] = []

        for requirement in (
            result.missing_requirements
        ):
            feedback.append(
                "Missing requirement: "
                f"{requirement}"
            )

        for issue in result.issues:
            feedback.append(
                "Semantic issue: "
                f"{issue}"
            )

        if not feedback:
            feedback.append(
                "The previous SQL did not "
                "fully satisfy the original "
                "question. Re-evaluate the "
                "complete request."
            )

        return tuple(feedback)

    @staticmethod
    def _build_semantic_clarification(
        result: SemanticValidationResult,
    ) -> str:

        if (
            result.missing_requirements
        ):
            details = "；".join(
                result.missing_requirements
            )

            return (
                "当前还缺少以下必要信息："
                f"{details}"
            )

        return (
            "当前上下文不足以可靠完成查询，"
            "请补充必要的业务信息。"
        )

    @staticmethod
    def _build_validation_clarification(
        missing_context: tuple[str, ...],
    ) -> str:

        if not missing_context:
            raise RuntimeError(
                "context_required must provide "
                "missing_context."
            )

        details = "；".join(
            missing_context
        )

        return (
            "为了继续完成当前查询，"
            "还需要确认以下信息："
            f"{details}"
        )

    def _request_clarification(
        self,
        state: QueryAgentState,
    ) -> dict:
        """暂停Graph并向用户请求必要Context。

        首次运行：
            interrupt(...) 暂停Graph。

        resume以后：
            interrupt(...) 返回用户提供的答案，
            节点继续向下执行。

        注意：
        interrupt之前不要执行不可重复的副作用，
        因为节点在resume时会重新执行到interrupt。
        """
        current_round = state.get(
            "clarification_round",
            0,
        )
        
        max_rounds = state.get(
            "max_clarification_rounds",
            self.max_clarification_rounds,
        )
        
        # 到达最大追问次数
        if current_round >= max_rounds:
            return {
                "success": False,

                "error_message": (
                    "Agent连续多次仍无法获得"
                    "足够上下文，任务停止。"
                ),

                "clarification_question": (
                    None
                ),
            }
            
        payload = {
            "type": "clarification",
            "question":(
                state.get(
                    "clarification_question"
                )
            ),
            "missing_context":(
                state.get(
                    "missing_context",
                    (),
                )
            ),
            "reason": (
                state.get(
                    "clarification_reason",
                    "",
                )
            ),
            "round":(
                current_round + 1
            ),
            "max_rounds":(
                max_rounds
            ),
        }
        
        # ========================================================
        # 第一次执行：
        # 这里暂停Graph。
        #
        # Resume时：
        # interrupt返回Command(resume=...)提供的值。
        # ========================================================

        # ========================================================
        # Public API
        # ========================================================
        
        answer = interrupt(payload)
        
        answer_text = str(answer).strip()
        
        if not answer_text:
            return {
                "success": False,
                "error_message":(
                    "用户未提供有效澄清信息。"
                ),
                "clarification_question":(
                    None
                ),
            }
            
        existing_context = (
            state.get(
                "session_context",
                (),
            )
        )
        
        new_session_context = (
            *existing_context,
            (
                "User clarification: "
                f"{answer_text}"
            ),
        )
        
        return {
            "session_context": (
                new_session_context
            ),

            "clarification_round": (
                current_round + 1
            ),

            # 清掉上一轮澄清状态。
            "clarification_question": None,

            "missing_context": (),

            "clarification_reason": "",

            # 如果来自Semantic FAIL/CLARIFY，
            # 不应该把上一轮修订反馈继续污染新一轮。
            "revision_feedback": (),

            "semantic_result": None,

            "semantic_validation_status": (
                None
            ),

            "trusted_sql": None,

            "success": False,

            "error_message": None,

            "generation_attempt":0,
        }


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
            self._build_initial_state(
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