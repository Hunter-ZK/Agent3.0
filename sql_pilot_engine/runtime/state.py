from __future__ import annotations

from typing_extensions import NotRequired, TypedDict

from sql_pilot_engine.context.builder import QueryContext
from sql_pilot_engine.generation.models import QueryPlan


class QueryAgentState(TypedDict):
    """Checkpoint-safe state shared by the Text-to-SQL LangGraph runtime.

    Runtime state is deliberately narrower than the domain model. In particular,
    ``LinkedSchema`` is not persisted because it embeds physical Metadata objects and
    read-only mappings that do not belong in a checkpoint serialization contract.
    Schema linking is deterministic, so downstream nodes re-link from ``query_plan``
    when they need the transient domain object.
    """

    # Input / identity
    question: str
    dialect: NotRequired[str]
    session_context: NotRequired[tuple[str, ...]]
    thread_id: str
    turn_id: str

    # Context / planning
    query_context: NotRequired[QueryContext | None]
    query_plan: NotRequired[QueryPlan | None]
    clarification_question: NotRequired[str | None]
    missing_context: NotRequired[tuple[str, ...]]
    clarification_reason: NotRequired[str]

    # HITL
    clarification_round: NotRequired[int]
    max_clarification_rounds: NotRequired[int]

    # Schema-linking checkpoint projection
    linking_resolved: NotRequired[bool]
    linking_failures: NotRequired[tuple[dict[str, str], ...]]
    linking_error_message: NotRequired[str | None]

    # Generation / compiler
    compilation_status: NotRequired[str | None]
    compilation_fallback_reason: NotRequired[str | None]
    compilation_evidence: NotRequired[dict[str, object] | None]
    generation_source: NotRequired[str | None]
    generated_sql: NotRequired[str | None]
    revision_feedback: NotRequired[tuple[str, ...]]
    generation_attempt: NotRequired[int]
    max_semantic_retries: NotRequired[int]

    # Trust
    candidate_sql: NotRequired[str | None]
    validation_status: NotRequired[str | None]
    validation_error_message: NotRequired[str | None]
    validation_issues: NotRequired[tuple[dict[str, object], ...]]

    # Semantic validation
    semantic_validation_status: NotRequired[str | None]
    semantic_missing_requirements: NotRequired[tuple[str, ...]]
    semantic_issues: NotRequired[tuple[str, ...]]

    # Final
    trusted_sql: NotRequired[str | None]
    success: NotRequired[bool]
    error_message: NotRequired[str | None]
