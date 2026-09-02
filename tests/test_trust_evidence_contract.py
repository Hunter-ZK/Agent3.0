from __future__ import annotations

from sql_pilot_engine.context.semantic.models import (
    SemanticModel,
)

from sql_pilot_engine.core.trust_evidence import (
    SQLTrustEvidence,
)

from sql_pilot_engine.engine import (
    SQLPilotEngine,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
)

from sql_pilot_engine.schemas.requests import (
    SQLReviewRequest,
)


def test_trust_evidence_preserves_task_contract(
) -> None:

    plan = QueryPlan(
        tables=("table_a",),
        dimensions=(),
        metrics=("metric_a",),
    )

    linked_schema = LinkedSchema(
        tables=(),
    )

    semantic_model = SemanticModel(
        tables=(),
        metrics=(),
    )

    evidence = SQLTrustEvidence(
        query_plan=plan,
        linked_schema=linked_schema,
        semantic_model=semantic_model,
    )

    assert (
        evidence.query_plan
        is plan
    )

    assert (
        evidence.linked_schema
        is linked_schema
    )

    assert (
        evidence.semantic_model
        is semantic_model
    )


def test_engine_keeps_same_trust_evidence(
) -> None:

    evidence = SQLTrustEvidence(
        query_plan=QueryPlan(
            tables=("table_a",),
            dimensions=(),
            metrics=(),
        ),

        linked_schema=LinkedSchema(
            tables=(),
        ),

        semantic_model=SemanticModel(
            tables=(),
            metrics=(),
        ),
    )

    request = SQLReviewRequest(
        sql="SELECT 1",

        trust_evidence=(
            evidence
        ),
    )

    context = (
        SQLPilotEngine
        ._build_execution_context(
            request
        )
    )

    assert (
        context.trust_evidence
        is evidence
    )