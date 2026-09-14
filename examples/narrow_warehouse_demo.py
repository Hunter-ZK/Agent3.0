from __future__ import annotations

from pathlib import Path

from sql_pilot_engine.context.semantic.loader import SemanticModelLoader
from sql_pilot_engine.generation.metric_compiler import MetricSQLCompiler
from sql_pilot_engine.generation.models import CompilationStatus, QueryPlan
from sql_pilot_engine.linking.schema_linker import SchemaLinker
from sql_pilot_engine.metadata.demo_provider import build_loan_demo_metadata_provider


def main() -> None:
    """Public V1 demo for deterministic narrow warehouse SQL development.

    This path deliberately contains no LLM. It demonstrates the V1 contract:

        approved semantic asset
            + QueryPlan
            + physical Metadata
            -> deterministic Schema Linking
            -> Metric SQL Compiler
            -> auditable SQL + CompilationEvidence
    """

    project_root = Path(__file__).resolve().parents[1]
    semantic_model = SemanticModelLoader().load(
        project_root
        / "sql_pilot_engine"
        / "context"
        / "semantic"
        / "loan_model.json"
    )

    provider = build_loan_demo_metadata_provider()
    linker = SchemaLinker(
        metadata_provider=provider,
        semantic_model=semantic_model,
    )
    compiler = MetricSQLCompiler(
        semantic_model=semantic_model,
    )

    plan = QueryPlan(
        tables=("ods_hd_100_cldkxx",),
        dimensions=("dt",),
        metrics=("tech_loan_balance",),
        filters=("dt = '202609'",),
        group_by=("dt",),
    )

    linked_schema = linker.link(plan=plan)
    if not linked_schema.resolved:
        raise RuntimeError(
            f"Schema linking failed: {linked_schema.failures!r}"
        )

    outcome = compiler.compile(
        plan=plan,
        linked_schema=linked_schema,
        dialect="maxcompute",
    )

    if outcome.status is not CompilationStatus.COMPILED:
        raise RuntimeError(
            "Narrow warehouse demo unexpectedly fell back: "
            f"{outcome.fallback_reason} {outcome.reason}"
        )
    if outcome.generated_sql is None or outcome.evidence is None:
        raise RuntimeError(
            "Compiled outcome must contain SQL and evidence."
        )

    print("=" * 72)
    print("Agent3.0 · Narrow Warehouse V1 Demo")
    print("=" * 72)
    print("\n[1] Query Plan")
    print(plan)
    print("\n[2] Physical Binding")
    for table in linked_schema.tables:
        print(table.metadata.full_name)
    print("\n[3] Deterministic SQL")
    print(outcome.generated_sql.sql)
    print("\n[4] Compilation Evidence")
    print(outcome.evidence)


if __name__ == "__main__":
    main()
