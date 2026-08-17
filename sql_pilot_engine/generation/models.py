from __future__ import annotations

from dataclasses import dataclass



@dataclass(frozen=True)
class QueryPlan:
    
    tables: tuple[str, ...]
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    filters: tuple[str, ...] = ()
    group_by: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    

@dataclass(frozen=True)
class PlanningClarification:

    clarification_question: str

    missing_context: tuple[str, ...] = ()

    reason: str = ""

    def __post_init__(self) -> None:
        if not (
            self.clarification_question.strip()
        ):
            raise ValueError(
                "clarification_question "
                "cannot be empty"
            )

QueryPlanningOutcome = (
    QueryPlan | PlanningClarification
)

@dataclass(frozen=True)
class GeneratedSQL:
    
    sql: str
    dialect: str
    
    def __post_init__(self) -> None:
        if not self.sql.strip():
            raise ValueError(
                "GeneratedSQL.sql cannot be empty."
            )