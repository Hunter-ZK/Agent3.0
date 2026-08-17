from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.generation.models import (
    QueryPlan,
)


@dataclass(frozen=True)
class TextToSQLRequest:
    question: str
    dialect: str = "maxcompute"

    session_context: tuple[str, ...] = ()
    
    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError(
                "TextToSQLRequest.question cannot be empty."
            )

        if any(
            not item.strip()
            for item
            in self.session_context
        ):
            raise ValueError(
                "session_context cannot "
                "contain empty items."
            )
            
@dataclass(frozen=True)
class TextToSQLResult:
    question: str
    query_plan: QueryPlan
    generated_sql: str
    trusted_sql: str | None
    success: bool
    validation_status: str
    semantic_validation_status: (
        str | None
    ) = None

    semantic_missing_requirements: (
        tuple[str, ...]
    ) = ()

    semantic_issues: (
        tuple[str, ...]
    ) = ()


@dataclass(frozen=True)
class TextToSQLClarification:

    question: str
    clarification_question: str

    missing_context: tuple[str, ...] = ()

    reason: str = ""

TextToSQLResponse = (
    TextToSQLResult | TextToSQLClarification
)