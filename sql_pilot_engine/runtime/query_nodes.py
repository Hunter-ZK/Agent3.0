from __future__ import annotations

from uuid import uuid4

import logging

from langgraph.types import interrupt

from sql_pilot_engine.generation.models import (
    PlanningClarification,
    CompilationStatus,
    GenerationSource,
)

from sql_pilot_engine.linking.schema_linker import (
    SchemaLinkingError,
)

from sql_pilot_engine.runtime.state import (
    QueryAgentState,
)

from sql_pilot_engine.services.text_to_sql_stage_service import (
    TextToSQLStageService,
)
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticValidationResult,
    SemanticValidationStatus,
)
from sql_pilot_engine.runtime.event import (
    RuntimeEvent,
    RuntimeEventType,
)

from sql_pilot_engine.runtime.event_bus import (
    EventBus,
)

logger = logging.getLogger(
    __name__
)



class QueryRuntimeNodes:
    """
    Text-to-SQL LangGraph Runtime Node Adapter。

    负责：

        QueryAgentState
            ↓
        TextToSQLStageService
            ↓
        QueryAgentState

    同时负责：
    - Runtime routing
    - retry state
    - clarification state
    - LangGraph interrupt

    不负责：
    - Context Retrieval 实现
    - Planning 实现
    - Schema Linking 实现
    - SQL Generation 实现
    - Trusted SQL 实现
    - Semantic Validation 实现
    - Graph topology
    - Checkpoint backend
    - start / resume
    """

    def __init__(
        self,
        *,
        stage_service: TextToSQLStageService,
        event_bus: EventBus,
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

        self.stage_service = stage_service
        self.event_bus = event_bus

        self.max_semantic_retries = (
            max_semantic_retries
        )

        self.max_clarification_rounds = (
            max_clarification_rounds
        )

    def _publish_event(
        self,
        *,
        state: QueryAgentState,
        event_type: RuntimeEventType,
        stage: str,
        data: dict[
            str,
            object,
        ] | None = None,
    ) -> None:
        """
        Runtime Event 的统一旁路出口。

        Event 失败不得改变
        Text-to-SQL 业务执行结果。
        """

        event = RuntimeEvent(
            event_type=event_type,

            capability=(
                "text_to_sql"
            ),

            thread_id=(
                state["thread_id"]
            ),

            turn_id=(
                state["turn_id"]
            ),

            stage=stage,

            data=(
                data
                if data is not None
                else {}
            ),
        )

        try:
            self.event_bus.publish(
                event
            )

        except Exception:
            logger.exception(
                (
                    "Runtime event publish "
                    "failed: type=%s stage=%s"
                ),
                event_type.value,
                stage,
            )

    # ========================================================
    # Node 1
    # Context Intelligence
    # ========================================================
    
    def retrieve_context(
            self,
            state: QueryAgentState,
    ) -> dict:

        question = state["question"]
        

        query_context = (
            self.stage_service.build_query_context(
                question=question,
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
    def plan_query(
        self,
        state: QueryAgentState,
    ) -> dict:


        query_context = state.get("query_context")

        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing"
                "before planning."
            )
        
        outcome = self.stage_service.plan(
            query_context=(
                query_context
            ),
        )
        
        if isinstance(
            outcome,
            PlanningClarification,
        ):

            self._publish_event(
                state=state,

                event_type=(
                    RuntimeEventType.PLAN
                ),

                stage="planning",

                data={
                    "status": (
                        "clarification_required"
                    ),
                },
            )

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
            "linking_failures": (),
            "linking_error_message": None,
        }

    # ========================================================
    # Node 3
    # Schema Linking
    # ========================================================
    
    def link_schema(
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
                self.stage_service.link_schema(
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

            failures = (
                linked_schema.failures
            )

            message = (
                self
                ._build_linking_error_message(
                    failures
                )
            )

            return {
                "linked_schema": (
                    linked_schema
                ),

                "linking_failures": (
                    failures
                ),

                "linking_error_message": (
                    message
                ),

                "error_message": (
                    message
                ),

                "success": False,
            }

        return {
            "linked_schema": (
                linked_schema
            ),

            "linking_failures": (),

            "linking_error_message": None,

            "error_message": None,
        }

    # ========================================================
    # Node 4
    # SQL Generation
    # ========================================================


    def compile_sql(
        self,
        state: QueryAgentState,
    ) -> dict:

        plan = state.get(
            "query_plan"
        )

        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing "
                "before Metric compilation."
            )

        linked_schema = state.get(
            "linked_schema"
        )

        if linked_schema is None:
            raise RuntimeError(
                "LinkedSchema is missing "
                "before Metric compilation."
            )

        outcome = (
            self.stage_service
            .try_compile_sql(
                plan=plan,

                linked_schema=(
                    linked_schema
                ),

                dialect=state.get(
                    "dialect",
                    "maxcompute",
                ),
            )
        )

        updates = {
            "compilation_status": (
                outcome.status.value
            ),

            "compilation_fallback_reason": (
                outcome
                .fallback_reason
                .value

                if (
                    outcome
                    .fallback_reason
                    is not None
                )

                else None
            ),

            "compilation_evidence": (
                outcome.evidence
            ),
        }

        if (
            outcome.status
            is CompilationStatus.COMPILED
        ):

            generated = (
                outcome.generated_sql
            )

            if generated is None:
                raise RuntimeError(
                    "Compiler returned "
                    "COMPILED without SQL."
                )

            # generation_attempt 表示
            # 已产生多少个 SQL Candidate，
            # 不只表示 LLM 调用次数。
            attempt = (
                state.get(
                    "generation_attempt",
                    0,
                )
                + 1
            )

            updates.update(
                {
                    "generated_sql": (
                        generated.sql
                    ),

                    "generation_source": (
                        GenerationSource
                        .COMPILED
                        .value
                    ),

                    "generation_attempt": (
                        attempt
                    ),
                }
            )

            return updates

        updates.update(
            {
                "generated_sql": None,

                "generation_source": None,
            }
        )

        return updates

    def generate_sql(
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
            self.stage_service.generate_sql(
                plan=plan,
                linked_schema=linked_schema,
                query_context=query_context,
                dialect=state.get("dialect","maxcompute"),
                revision_feedback=state.get("revision_feedback",(),),
            )
        )
        
        return {
            "generated_sql": (
                result.sql
            ),

            "generation_attempt": (
                attempt
            ),

            "generation_source": (
                GenerationSource
                .LLM
                .value
            ),
        }

    # ========================================================
    # Node 4
    # Trusted SQL Workflow
    # ========================================================

    def trust_sql(
        self,
        state: QueryAgentState,
    ) -> dict:

        plan = state.get(
            "query_plan"
        )

        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing "
                "before Trusted SQL workflow."
            )

        linked_schema = state.get(
            "linked_schema"
        )

        if linked_schema is None:
            raise RuntimeError(
                "LinkedSchema is missing "
                "before Trusted SQL workflow."
            )

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

        generation_source_value = (
            state.get(
                "generation_source"
            )
        )

        if not generation_source_value:
            raise RuntimeError(
                "generation_source is missing "
                "before Trusted SQL workflow."
            )

        try:
            generation_source = (
                GenerationSource(
                    generation_source_value
                )
            )

        except ValueError as exc:
            raise RuntimeError(
                "Invalid generation_source: "
                f"{generation_source_value}"
            ) from exc

        trust_result = (
            self.stage_service.trust_sql(
                generated_sql=generated_sql,
                dialect=state.get(
                    "dialect",
                    "maxcompute",
                ),
                query_context=query_context,
                plan=plan,
                linked_schema=linked_schema,
            )
        )
        
        
        missing_context = tuple(
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

        self._publish_event(
            state=state,

            event_type=(
                RuntimeEventType.VALIDATION
            ),

            stage="trusted_sql",

            data={
                "status": (
                    trust_result.final_status
                ),
            },
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
            
            "validation_issues": tuple(
                trust_result.validation_issues
                or ()
            ),

            "missing_context": (
                missing_context
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
                            missing_context
                        )
                    ),

                    "missing_context": (
                        missing_context
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
    

    def semantic_validate(
        self,
        state: QueryAgentState,
    ) -> dict:
        
        # if self.stage_service is None:
        #     return {
        #         "semantic_result": None,
        #         "semantic_validation_status": None,
        #         "trusted_sql":state.get("candidate_sql",""),
        #         "success":state.get("candidate_sql") is not None,
        #     }
            
        result = (
            self.stage_service.validate_semantics(
                sql=state["candidate_sql"],
                plan=state["query_plan"],
                query_context=state["query_context"],
            )
        )
        
        if result is None:

            success = (
                state.get(
                    "candidate_sql"
                )
                is not None
            )

            if success:
                self._publish_event(
                    state=state,

                    event_type=(
                        RuntimeEventType
                        .AGENT_RESULT
                    ),

                    stage="result",

                    data={
                        "success": True,
                    },
                )

            return {
                "semantic_result": None,

                "semantic_validation_status": None,

                "trusted_sql": (
                    state.get(
                        "candidate_sql",
                        "",
                    )
                ),

                "success": success,
            }

        self._publish_event(
            state=state,

            event_type=(
                RuntimeEventType.VALIDATION
            ),

            stage=(
                "semantic_validation"
            ),

            data={
                "status": (
                    result.status.value
                ),
            },
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

            self._publish_event(
                state=state,

                event_type=(
                    RuntimeEventType.AGENT_RESULT
                ),

                stage="result",

                data={
                    "success": True,
                },
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
                    self.build_revision_feedback(
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
    def route_after_plan(
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
    def route_after_linking(
        state: QueryAgentState,
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
        
        return "compile"

    @staticmethod
    def route_after_compilation(
        state: QueryAgentState,
    ) -> str:

        status = state.get(
            "compilation_status"
        )

        if (
            status
            == (
                CompilationStatus
                .COMPILED
                .value
            )
        ):
            return "trust"

        if (
            status
            == (
                CompilationStatus
                .NOT_COMPILABLE
                .value
            )
        ):
            return "generate"

        raise RuntimeError(
            "Metric Compiler finished "
            "without a valid status."
        )

    @staticmethod
    def route_after_trust(
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
    def route_after_semantic_validation(
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
    def route_after_clarification(
        state: QueryAgentState,
    ) -> str:

        if state.get(
            "error_message"
        ):
            return "end"

        return "continue"

    def request_clarification(
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




    @staticmethod
    def build_revision_feedback(
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
    def build_semantic_clarification(
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
    def build_validation_clarification(
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


    @staticmethod
    def _build_linking_error_message(
        failures,
    ) -> str:

        if not failures:
            return (
                "Schema linking failed."
            )

        details = "; ".join(
            (
                f"{failure.code.value}: "
                f"{failure.term}"
            )
            for failure
            in failures
        )

        return (
            "Schema linking failed: "
            f"{details}"
        )


    # ========================================================
    # Helpers
    # ========================================================

    def build_initial_state(
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

        state =  {
            # Runtime Identity
            "thread_id": thread_id,
            "turn_id": str(uuid4()),

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
            "compilation_status": None,

            "compilation_fallback_reason": (
                None
            ),

            "compilation_evidence": None,

            "generation_source": None,

            "generated_sql": None,            

            "generated_sql": None,
            "revision_feedback": (),
            "generation_attempt": 0,
            "max_semantic_retries": (
                self.max_semantic_retries
            ),

            "validation_status": None,
            "validation_error_message": None,
            "validation_issues": (),

            "candidate_sql": None,

            "semantic_validation_status": None,
            "semantic_missing_requirements": (),
            "semantic_issues": (),

            # Final
            "trusted_sql": None,
            "success": False,
            "error_message": None,
        }

        self._publish_event(
            state = state,

            event_type = (
                RuntimeEventType.USER_MESSAGE
            ),

            stage = "input",

            data = {
                "status": "received",
            },
        )

        return state
    