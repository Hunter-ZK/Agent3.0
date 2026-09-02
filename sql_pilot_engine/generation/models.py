from __future__ import annotations

from dataclasses import dataclass

from enum import Enum

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
            

class CompilationStatus(
    str,
    Enum,
):
    COMPILED = "compiled"
    
    NOT_COMPILABLE = "not_compilable"
    
    
class GenerationSource(
    str,
    Enum,
):
    COMPILED = "compiled"
    LLM = "llm"
    
class CompilationFallbackReason(
    str,
    Enum,
):
    NO_METRIC = "no_metric"

    MULTI_TABLE = "multi_table"

    COMPLEX_EXPRESSION = (
        "complex_expression"
    )

    UNSUPPORTED_AGGREGATION = (
        "unsupported_aggregation"
    )

    UNSUPPORTED_FILTER = (
        "unsupported_filter"
    )

    UNRESOLVED_SCHEMA = (
        "unresolved_schema"
    )

    INVALID_GROUPING = (
        "invalid_grouping"
    )


@dataclass(frozen=True)
class CompilationEvidence:
    """
    Metric Compiler 的确定性生成证据。

    表示 SQL 中每一类关键结构
    来自哪些已解析的结构化事实。
    """
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


@dataclass(frozen=True)
class MetricCompilationOutcome:

    status: CompilationStatus

    generated_sql: (
        GeneratedSQL | None
    ) = None

    evidence: (
        CompilationEvidence | None
    ) = None

    fallback_reason: (
        CompilationFallbackReason
        | None
    ) = None

    reason: str = ""

    def __post_init__(
        self,
    ) -> None:

        if (
            self.status
            is CompilationStatus.COMPILED
        ):
            if self.generated_sql is None:
                raise ValueError(
                    "COMPILED outcome must "
                    "contain generated_sql."
                )

            if self.evidence is None:
                raise ValueError(
                    "COMPILED outcome must "
                    "contain evidence."
                )

            if (
                self.fallback_reason
                is not None
            ):
                raise ValueError(
                    "COMPILED outcome cannot "
                    "contain fallback_reason."
                )

            return

        if self.generated_sql is not None:
            raise ValueError(
                "NOT_COMPILABLE outcome "
                "cannot contain generated_sql."
            )

        if self.evidence is not None:
            raise ValueError(
                "NOT_COMPILABLE outcome "
                "cannot contain evidence."
            )

        if self.fallback_reason is None:
            raise ValueError(
                "NOT_COMPILABLE outcome "
                "must contain fallback_reason."
            )
            
    @classmethod
    def compiled(
        cls,
        *,
        generated_sql: GeneratedSQL,
        evidence: CompilationEvidence,
    ) -> "MetricCompilationOutcome":

        return cls(
            status=(
                CompilationStatus.COMPILED
            ),

            generated_sql=(
                generated_sql
            ),

            evidence=evidence,
        )

    @classmethod
    def fallback(
        cls,
        *,
        fallback_reason: (
            CompilationFallbackReason
        ),
        reason: str,
    ) -> "MetricCompilationOutcome":

        return cls(
            status=(
                CompilationStatus
                .NOT_COMPILABLE
            ),

            fallback_reason=(
                fallback_reason
            ),

            reason=reason,
        )