from __future__ import annotations

import logging
from uuid import uuid4

from langgraph.types import interrupt

from sql_pilot_engine.generation.models import (
    CompilationEvidence,
    CompilationStatus,
    GenerationSource,
    PlanningClarification,
)
from sql_pilot_engine.linking.models import LinkedSchema
from sql_pilot_engine.linking.schema_linker import SchemaLinkingError
from sql_pilot_engine.runtime.event import RuntimeEvent, RuntimeEventType
from sql_pilot_engine.runtime.event_bus import EventBus
from sql_pilot_engine.runtime.state import QueryAgentState
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticValidationResult,
    SemanticValidationStatus,
)
from sql_pilot_engine.services.text_to_sql_stage_service import TextToSQLStageService


logger = logging.getLogger(__name__)


class QueryRuntimeNodes:
    """LangGraph state/routing adapter for the Text-to-SQL capability.

    Domain objects that are not part of the checkpoint contract stay transient. In
    particular, ``LinkedSchema`` is re-derived deterministically from ``QueryPlan``
    whenever Compiler, Generator, or Trust needs it. The checkpoint stores only the
    stable outcome of linking and serializable diagnostics.
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
            raise ValueError("max_semantic_retries must be >= 0")
        if max_clarification_rounds <= 0:
            raise ValueError("max_clarification_rounds must be greater than 0")

        self.stage_service = stage_service
        self.event_bus = event_bus
        self.max_semantic_retries = max_semantic_retries
        self.max_clarification_rounds = max_clarification_rounds

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def _publish_event(
        self,
        *,
        state: QueryAgentState,
        event_type: RuntimeEventType,
        stage: str,
        data: dict[str, object] | None = None,
    ) -> None:
        event = RuntimeEvent(
            event_type=event_type,
            capability="text_to_sql",
            thread_id=state["thread_id"],
            turn_id=state["turn_id"],
            stage=stage,
            data=data if data is not None else {},
        )
        try:
            self.event_bus.publish(event)
        except Exception:
            logger.exception(
                "Runtime event publish failed: type=%s stage=%s",
                event_type.value,
                stage,
            )

    # ------------------------------------------------------------------
    # Context / Planning
    # ------------------------------------------------------------------

    def retrieve_context(self, state: QueryAgentState) -> dict:
        return {
            "query_context": self.stage_service.build_query_context(
                question=state["question"],
                session_context=state.get("session_context", ()),
            )
        }

    def plan_query(self, state: QueryAgentState) -> dict:
        query_context = state.get("query_context")
        if query_context is None:
            raise RuntimeError("QueryContext is missing before planning.")

        outcome = self.stage_service.plan(query_context=query_context)

        if isinstance(outcome, PlanningClarification):
            self._publish_event(
                state=state,
                event_type=RuntimeEventType.PLAN,
                stage="planning",
                data={"status": "clarification_required"},
            )
            return {
                "query_plan": None,
                "clarification_question": outcome.clarification_question,
                "missing_context": outcome.missing_context,
                "clarification_reason": outcome.reason,
                "linking_resolved": False,
                "linking_failures": (),
                "linking_error_message": None,
                "success": False,
            }

        return {
            "query_plan": outcome,
            "clarification_question": None,
            "missing_context": (),
            "clarification_reason": "",
            "linking_resolved": False,
            "linking_failures": (),
            "linking_error_message": None,
            "error_message": None,
            "success": False,
        }

    # ------------------------------------------------------------------
    # Schema Linking
    # ------------------------------------------------------------------

    def link_schema(self, state: QueryAgentState) -> dict:
        plan = state.get("query_plan")
        if plan is None:
            raise RuntimeError("QueryPlan is missing before schema linking.")

        try:
            linked_schema = self.stage_service.link_schema(plan=plan)
        except SchemaLinkingError as exc:
            message = str(exc)
            return {
                "linking_resolved": False,
                "linking_failures": (),
                "linking_error_message": message,
                "error_message": message,
                "success": False,
            }

        if not linked_schema.resolved:
            message = self._build_linking_error_message(linked_schema.failures)
            return {
                "linking_resolved": False,
                "linking_failures": self._serialize_linking_failures(
                    linked_schema
                ),
                "linking_error_message": message,
                "error_message": message,
                "success": False,
            }

        return {
            "linking_resolved": True,
            "linking_failures": (),
            "linking_error_message": None,
            "error_message": None,
        }

    def _resolved_linked_schema(self, state: QueryAgentState) -> LinkedSchema:
        """Rebuild the transient physical binding after the checkpoint boundary."""

        if not state.get("linking_resolved", False):
            raise RuntimeError(
                "Resolved schema linking is required before downstream stages."
            )

        plan = state.get("query_plan")
        if plan is None:
            raise RuntimeError("QueryPlan is missing while rebuilding LinkedSchema.")

        try:
            linked_schema = self.stage_service.link_schema(plan=plan)
        except SchemaLinkingError as exc:
            raise RuntimeError(
                "Schema linking could not be reproduced after checkpoint."
            ) from exc

        if not linked_schema.resolved:
            raise RuntimeError(
                "Schema linking changed from resolved to unresolved within one turn."
            )

        return linked_schema

    @staticmethod
    def _serialize_linking_failures(
        linked_schema: LinkedSchema,
    ) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "code": failure.code.value,
                "term": failure.term,
                "message": failure.message,
            }
            for failure in linked_schema.failures
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def compile_sql(self, state: QueryAgentState) -> dict:
        plan = state.get("query_plan")
        if plan is None:
            raise RuntimeError("QueryPlan is missing before Metric compilation.")

        linked_schema = self._resolved_linked_schema(state)
        outcome = self.stage_service.try_compile_sql(
            plan=plan,
            linked_schema=linked_schema,
            dialect=state.get("dialect", "maxcompute"),
        )

        updates: dict[str, object] = {
            "compilation_status": outcome.status.value,
            "compilation_fallback_reason": (
                outcome.fallback_reason.value
                if outcome.fallback_reason is not None
                else None
            ),
            "compilation_evidence": self._serialize_compilation_evidence(
                outcome.evidence
            ),
        }

        if outcome.status is CompilationStatus.COMPILED:
            generated = outcome.generated_sql
            if generated is None:
                raise RuntimeError("Compiler returned COMPILED without SQL.")

            updates.update(
                {
                    "generated_sql": generated.sql,
                    "generation_source": GenerationSource.COMPILED.value,
                    "generation_attempt": state.get("generation_attempt", 0) + 1,
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

    @staticmethod
    def _serialize_compilation_evidence(
        evidence: CompilationEvidence | None,
    ) -> dict[str, object] | None:
        if evidence is None:
            return None
        return {
            "metric_names": evidence.metric_names,
            "physical_table": evidence.physical_table,
            "metric_expressions": evidence.metric_expressions,
            "dimension_columns": evidence.dimension_columns,
            "filter_expressions": evidence.filter_expressions,
            "group_by_columns": evidence.group_by_columns,
        }

    def generate_sql(self, state: QueryAgentState) -> dict:
        query_context = state.get("query_context")
        plan = state.get("query_plan")
        if query_context is None:
            raise RuntimeError("QueryContext is missing before SQL generation.")
        if plan is None:
            raise RuntimeError("QueryPlan is missing before SQL generation.")

        linked_schema = self._resolved_linked_schema(state)
        result = self.stage_service.generate_sql(
            plan=plan,
            linked_schema=linked_schema,
            query_context=query_context,
            dialect=state.get("dialect", "maxcompute"),
            revision_feedback=state.get("revision_feedback", ()),
        )

        return {
            "generated_sql": result.sql,
            "generation_attempt": state.get("generation_attempt", 0) + 1,
            "generation_source": GenerationSource.LLM.value,
        }

    # ------------------------------------------------------------------
    # Trusted SQL
    # ------------------------------------------------------------------

    def trust_sql(self, state: QueryAgentState) -> dict:
        plan = state.get("query_plan")
        query_context = state.get("query_context")
        generated_sql = state.get("generated_sql")

        if plan is None:
            raise RuntimeError("QueryPlan is missing before Trusted SQL workflow.")
        if query_context is None:
            raise RuntimeError("QueryContext is missing before Trusted SQL workflow.")
        if not generated_sql:
            raise RuntimeError("Generated SQL is missing before Trusted SQL workflow.")

        generation_source_value = state.get("generation_source")
        if not generation_source_value:
            raise RuntimeError(
                "generation_source is missing before Trusted SQL workflow."
            )
        try:
            generation_source = GenerationSource(generation_source_value)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid generation_source: {generation_source_value}"
            ) from exc

        linked_schema = self._resolved_linked_schema(state)
        trust_result = self.stage_service.trust_sql(
            generated_sql=generated_sql,
            dialect=state.get("dialect", "maxcompute"),
            query_context=query_context,
            plan=plan,
            linked_schema=linked_schema,
            generation_source=generation_source,
        )

        missing_context = tuple(trust_result.missing_context or ())
        if trust_result.success and not trust_result.trusted_sql:
            raise RuntimeError(
                "TrustedSQLWorkflow succeeded without trusted_sql."
            )

        self._publish_event(
            state=state,
            event_type=RuntimeEventType.VALIDATION,
            stage="trusted_sql",
            data={"status": trust_result.final_status},
        )

        updates: dict[str, object] = {
            "validation_status": trust_result.final_status,
            "validation_error_message": trust_result.error_message,
            "validation_issues": tuple(trust_result.validation_issues or ()),
            "candidate_sql": trust_result.trusted_sql,
            "trusted_sql": None,
            "success": False,
        }

        if trust_result.final_status == "context_required":
            updates.update(
                {
                    "clarification_question": self._build_validation_clarification(
                        missing_context
                    ),
                    "missing_context": missing_context,
                    "clarification_reason": (
                        trust_result.error_message
                        or "Trusted SQL 审查发现仍缺少必要业务上下文。"
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

    # ------------------------------------------------------------------
    # Semantic validation
    # ------------------------------------------------------------------

    def semantic_validate(self, state: QueryAgentState) -> dict:
        candidate_sql = state.get("candidate_sql")
        plan = state.get("query_plan")
        query_context = state.get("query_context")

        if not candidate_sql:
            raise RuntimeError(
                "candidate_sql is missing before Semantic Validation."
            )
        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing before Semantic Validation."
            )
        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing before Semantic Validation."
            )

        result = self.stage_service.validate_semantics(
            sql=candidate_sql,
            plan=plan,
            query_context=query_context,
        )

        if result is None:
            self._publish_event(
                state=state,
                event_type=RuntimeEventType.AGENT_RESULT,
                stage="result",
                data={"success": True},
            )
            return {
                "semantic_validation_status": None,
                "semantic_missing_requirements": (),
                "semantic_issues": (),
                "trusted_sql": candidate_sql,
                "success": True,
            }

        self._publish_event(
            state=state,
            event_type=RuntimeEventType.VALIDATION,
            stage="semantic_validation",
            data={"status": result.status.value},
        )

        updates: dict[str, object] = {
            "semantic_validation_status": result.status.value,
            "semantic_missing_requirements": tuple(result.missing_requirements),
            "semantic_issues": tuple(result.issues),
        }

        if result.passed:
            updates.update(
                {
                    "trusted_sql": candidate_sql,
                    "success": True,
                    "revision_feedback": (),
                }
            )
            self._publish_event(
                state=state,
                event_type=RuntimeEventType.AGENT_RESULT,
                stage="result",
                data={"success": True},
            )
            return updates

        if result.status is SemanticValidationStatus.NEED_CLARIFICATION:
            updates.update(
                {
                    "trusted_sql": None,
                    "success": False,
                    "clarification_question": self._build_semantic_clarification(
                        result
                    ),
                    "missing_context": tuple(result.missing_requirements),
                }
            )
            return updates

        updates.update(
            {
                "trusted_sql": None,
                "success": False,
                "revision_feedback": self.build_revision_feedback(result),
            }
        )
        return updates

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    @staticmethod
    def route_after_plan(state: QueryAgentState) -> str:
        if state.get("error_message"):
            return "end"
        if state.get("clarification_question"):
            return "clarify"
        return "link"

    @staticmethod
    def route_after_linking(state: QueryAgentState) -> str:
        if state.get("error_message"):
            return "end"
        return "compile" if state.get("linking_resolved", False) else "end"

    @staticmethod
    def route_after_compilation(state: QueryAgentState) -> str:
        status = state.get("compilation_status")
        if status == CompilationStatus.COMPILED.value:
            return "trust"
        if status == CompilationStatus.NOT_COMPILABLE.value:
            return "generate"
        raise RuntimeError(
            "Metric Compiler finished without a valid status."
        )

    @staticmethod
    def route_after_trust(state: QueryAgentState) -> str:
        if state.get("validation_status") == "context_required":
            if not state.get("missing_context"):
                raise RuntimeError(
                    "Trusted SQL returned context_required without missing_context."
                )
            return "clarify"
        if state.get("candidate_sql") is None:
            return "end"
        return "semantic_validate"

    @staticmethod
    def route_after_semantic_validation(state: QueryAgentState) -> str:
        status = state.get("semantic_validation_status")
        if status is None or status == SemanticValidationStatus.PASS.value:
            return "end"
        if status == SemanticValidationStatus.NEED_CLARIFICATION.value:
            return "clarify"

        if state.get("generation_attempt", 0) <= state.get(
            "max_semantic_retries",
            0,
        ):
            return "retry"
        return "end"

    @staticmethod
    def route_after_clarification(state: QueryAgentState) -> str:
        return "end" if state.get("error_message") else "continue"

    # ------------------------------------------------------------------
    # HITL
    # ------------------------------------------------------------------

    def request_clarification(self, state: QueryAgentState) -> dict:
        current_round = state.get("clarification_round", 0)
        max_rounds = state.get(
            "max_clarification_rounds",
            self.max_clarification_rounds,
        )

        if current_round >= max_rounds:
            return {
                "success": False,
                "error_message": "Agent连续多次仍无法获得足够上下文，任务停止。",
                "clarification_question": None,
            }

        payload = {
            "type": "clarification",
            "question": state.get("clarification_question"),
            "missing_context": state.get("missing_context", ()),
            "reason": state.get("clarification_reason", ""),
            "round": current_round + 1,
            "max_rounds": max_rounds,
        }

        answer_text = str(interrupt(payload)).strip()
        if not answer_text:
            return {
                "success": False,
                "error_message": "用户未提供有效澄清信息。",
                "clarification_question": None,
            }

        new_session_context = (
            *state.get("session_context", ()),
            f"User clarification: {answer_text}",
        )

        return {
            "session_context": new_session_context,
            "clarification_round": current_round + 1,
            "query_context": None,
            "query_plan": None,
            "linking_resolved": False,
            "linking_failures": (),
            "linking_error_message": None,
            "clarification_question": None,
            "missing_context": (),
            "clarification_reason": "",
            "compilation_status": None,
            "compilation_fallback_reason": None,
            "compilation_evidence": None,
            "generation_source": None,
            "generated_sql": None,
            "revision_feedback": (),
            "generation_attempt": 0,
            "validation_status": None,
            "validation_error_message": None,
            "validation_issues": (),
            "candidate_sql": None,
            "semantic_validation_status": None,
            "semantic_missing_requirements": (),
            "semantic_issues": (),
            "trusted_sql": None,
            "success": False,
            "error_message": None,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_revision_feedback(
        result: SemanticValidationResult,
    ) -> tuple[str, ...]:
        feedback = [
            f"Missing requirement: {item}"
            for item in result.missing_requirements
        ]
        feedback.extend(
            f"Semantic issue: {item}"
            for item in result.issues
        )
        if not feedback:
            feedback.append(
                "The previous SQL did not fully satisfy the original question. "
                "Re-evaluate the complete request."
            )
        return tuple(feedback)

    @staticmethod
    def _build_semantic_clarification(
        result: SemanticValidationResult,
    ) -> str:
        if result.missing_requirements:
            return (
                "当前还缺少以下必要信息："
                + "；".join(result.missing_requirements)
            )
        return "当前上下文不足以可靠完成查询，请补充必要的业务信息。"

    @staticmethod
    def _build_validation_clarification(
        missing_context: tuple[str, ...],
    ) -> str:
        if not missing_context:
            raise RuntimeError(
                "context_required must provide missing_context."
            )
        return (
            "为了继续完成当前查询，还需要确认以下信息："
            + "；".join(missing_context)
        )

    @staticmethod
    def _build_linking_error_message(failures) -> str:
        if not failures:
            return "Schema linking failed."
        return "Schema linking failed: " + "; ".join(
            f"{failure.code.value}: {failure.term}"
            for failure in failures
        )

    # ------------------------------------------------------------------
    # Initial state
    # ------------------------------------------------------------------

    def build_initial_state(
        self,
        *,
        thread_id: str,
        question: str,
        dialect: str,
        session_context: tuple[str, ...],
    ) -> QueryAgentState:
        state: QueryAgentState = {
            "thread_id": thread_id,
            "turn_id": str(uuid4()),
            "question": question,
            "dialect": dialect,
            "session_context": session_context,
            "query_context": None,
            "query_plan": None,
            "clarification_question": None,
            "missing_context": (),
            "clarification_reason": "",
            "clarification_round": 0,
            "max_clarification_rounds": self.max_clarification_rounds,
            "linking_resolved": False,
            "linking_failures": (),
            "linking_error_message": None,
            "compilation_status": None,
            "compilation_fallback_reason": None,
            "compilation_evidence": None,
            "generation_source": None,
            "generated_sql": None,
            "revision_feedback": (),
            "generation_attempt": 0,
            "max_semantic_retries": self.max_semantic_retries,
            "validation_status": None,
            "validation_error_message": None,
            "validation_issues": (),
            "candidate_sql": None,
            "semantic_validation_status": None,
            "semantic_missing_requirements": (),
            "semantic_issues": (),
            "trusted_sql": None,
            "success": False,
            "error_message": None,
        }

        self._publish_event(
            state=state,
            event_type=RuntimeEventType.USER_MESSAGE,
            stage="input",
            data={"status": "received"},
        )
        return state
