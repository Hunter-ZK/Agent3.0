from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    SchemaLinkingFailure,
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

    generation_source: (
        str | None
    ) = None

    compilation_status: (
        str | None
    ) = None

    compilation_fallback_reason: (
        str | None
    ) = None

    compilation_evidence: (
        TextToSQLCompilationEvidence
        | None
    ) = None

    linking_failures: tuple[
        SchemaLinkingFailure,
        ...
    ] = ()

    linking_error_message: (
        str | None
    ) = None

    validation_status: str = (
        "not_run"
    )
    validation_error_message: str | None = None
    validation_issues: tuple[
        TextToSQLValidationIssue,
        ...
    ] = ()
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

    thread_id: str | None = None

    missing_context: tuple[str, ...] = ()

    reason: str = ""

TextToSQLResponse = (
    TextToSQLResult | TextToSQLClarification
)


@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLValidationIssue:
    """
    Text-to-SQL 对 SQL Trust Issue
    的稳定 Application Projection。

    不直接把内部 ReviewResult /
    Issue 暴露给 Capability 调用方。
    """

    rule_id: str

    source: str

    severity: str

    action: str

    category: str

    message: str

    evidence: str

    def __post_init__(
        self,
    ) -> None:

        if not self.rule_id.strip():
            raise ValueError(
                "rule_id cannot be empty"
            )
            
            
@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLCompilationEvidence:

    metric_names: tuple[
        str,
        ...
    ]

    physical_table: str

    metric_expressions: tuple[
        str,
        ...
    ]

    dimension_columns: tuple[
        str,
        ...
    ] = ()

    filter_expressions: tuple[
        str,
        ...
    ] = ()

    group_by_columns: tuple[
        str,
        ...
    ] = ()