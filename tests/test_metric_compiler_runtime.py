from __future__ import annotations

from sql_pilot_engine.generation.models import (
    CompilationEvidence,
    CompilationFallbackReason,
    GeneratedSQL,
    GenerationSource,
    MetricCompilationOutcome,
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
)

from sql_pilot_engine.runtime.query_nodes import (
    QueryRuntimeNodes,
)


class SilentEventBus:

    def publish(
        self,
        event,
    ) -> None:
        _ = event


class CompilingStageService:

    def try_compile_sql(
        self,
        *,
        plan,
        linked_schema,
        dialect,
    ):

        _ = plan
        _ = linked_schema

        return (
            MetricCompilationOutcome
            .compiled(
                generated_sql=(
                    GeneratedSQL(
                        sql="SELECT 1",
                        dialect=dialect,
                    )
                ),

                evidence=(
                    CompilationEvidence(
                        metric_names=(
                            "metric_a",
                        ),

                        physical_table=(
                            "table_a"
                        ),

                        metric_expressions=(
                            "SUM(value)",
                        ),
                    )
                ),
            )
        )


class FallbackStageService:

    def try_compile_sql(
        self,
        *,
        plan,
        linked_schema,
        dialect,
    ):

        _ = plan
        _ = linked_schema
        _ = dialect

        return (
            MetricCompilationOutcome
            .fallback(
                fallback_reason=(
                    CompilationFallbackReason
                    .COMPLEX_EXPRESSION
                ),

                reason=(
                    "complex metric"
                ),
            )
        )


def _state():

    return {
        "thread_id": "test",
        "turn_id": "turn",

        "query_plan": QueryPlan(
            tables=("table_a",),
            dimensions=(),
            metrics=("metric_a",),
        ),

        "linked_schema": (
            LinkedSchema(
                tables=()
            )
        ),

        "dialect": "maxcompute",

        "generation_attempt": 0,
    }


def test_compiled_sql_routes_directly_to_trust():

    nodes = QueryRuntimeNodes(
        stage_service=(
            CompilingStageService()
        ),

        event_bus=(
            SilentEventBus()
        ),
    )

    updates = (
        nodes.compile_sql(
            _state()
        )
    )

    combined = {
        **_state(),
        **updates,
    }

    assert (
        updates[
            "generation_source"
        ]
        == (
            GenerationSource
            .COMPILED
            .value
        )
    )

    assert (
        updates[
            "generation_attempt"
        ]
        == 1
    )

    assert (
        nodes
        .route_after_compilation(
            combined
        )
        == "trust"
    )


def test_not_compilable_routes_to_llm_generator():

    nodes = QueryRuntimeNodes(
        stage_service=(
            FallbackStageService()
        ),

        event_bus=(
            SilentEventBus()
        ),
    )

    updates = (
        nodes.compile_sql(
            _state()
        )
    )

    combined = {
        **_state(),
        **updates,
    }

    assert (
        updates[
            "generated_sql"
        ]
        is None
    )

    assert (
        updates[
            "generation_source"
        ]
        is None
    )

    assert (
        nodes
        .route_after_compilation(
            combined
        )
        == "generate"
    )