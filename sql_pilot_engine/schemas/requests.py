from dataclasses import dataclass, field
from typing import Any

from sql_pilot_engine.context.builder import QueryContext
from sql_pilot_engine.core.trust_evidence import SQLTrustEvidence


@dataclass
class SQLReviewRequest:
    """External request contract for SQL Review / Trusted SQL capabilities."""

    sql: str
    file_path: str = "<memory>"
    mode: str = "prod"
    dialect: str = "maxcompute"
    categories: set[str] | None = None
    enable_metadata: bool = False
    enable_llm: bool = False
    llm_provider: str = "mock"
    metadata_provider: Any | None = None
    trace_id: str | None = None
    query_context: QueryContext | None = None
    trust_evidence: SQLTrustEvidence | None = None
    rule_packs: tuple[str, ...] = ()


@dataclass
class SQLFixRequest(SQLReviewRequest):
    """
    SQL Fix request.

    Fix always starts from Review evidence. LLM output remains a candidate and must
    re-enter Review / Critic / HITL before it can become Trusted SQL.
    """

    fix_provider: str = "auto"
    critic_feedback: list[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class SQLExplainRequest(SQLReviewRequest):
    """
    Production SQL Explain request.

    Explain is evidence-first: deterministic Program / Metadata / Lineage / Hint facts
    are primary. LLM is optional semantic narration and cannot override structural facts.
    """

    pass


@dataclass
class SQLOptimizeRequest(SQLReviewRequest):
    """
    Production SQL Optimize request.

    Optimization suggestions may be returned without a rewrite. Any candidate SQL is
    structurally gated and re-reviewed; runtime performance gains are not claimed without
    execution/statistics evidence.
    """

    optimization_goals: list[str] = field(default_factory=list)
