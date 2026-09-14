from __future__ import annotations

from typing import Any

from sql_pilot_engine.core.execution_context import (
    SQLExecutionContext,
)
from sql_pilot_engine.evidence.program_context import (
    ProgramEvidenceContext,
    ProgramEvidenceContextBuilder,
)
from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
)
from sql_pilot_engine.schemas.responses import (
    SQLExplainResponse,
)
from sql_pilot_engine.llm.explainer import (
    LLMExplainer,
)


class ExplainService:
    """
    Production SQL Explain。

    Deterministic Program/Evidence 是主事实层；LLM 只是可选语义增强层。
    因此：
    - 没有 LLM 仍可 Explain；
    - 超长 SQL 不再依赖模型 one-shot 理解；
    - LLM 不允许覆盖 table / CTE / lineage 等确定性结构事实。
    """

    def __init__(
        self,
        llm_client: StructuredGenerationModel | None = None,
        context_builder: ProgramEvidenceContextBuilder | None = None,
    ) -> None:
        self._explainer = (
            LLMExplainer(client=llm_client)
            if llm_client is not None
            else None
        )
        self._context_builder = (
            context_builder
            or ProgramEvidenceContextBuilder()
        )

    def explain(
        self,
        context: SQLExecutionContext,
    ) -> SQLExplainResponse:
        try:
            program_context = self._context_builder.build(
                context.sql,
                dialect=context.dialect,
                metadata_provider=context.metadata_provider,
            )

            deterministic = self._deterministic_response(
                context=context,
                program_context=program_context,
            )

            if (
                self._explainer is None
                or not context.enable_llm
            ):
                return deterministic

            payload = self._explainer.explain(
                sql=context.sql,
                evidence_context=program_context.render_for_llm(),
            )

            return self._merge_llm_enrichment(
                deterministic=deterministic,
                payload=payload,
            )

        except Exception as error:
            return SQLExplainResponse.failed(
                file_path=context.file_path,
                trace_id=context.trace_id,
                error_message=str(error),
            )

    @staticmethod
    def _deterministic_response(
        *,
        context: SQLExecutionContext,
        program_context: ProgramEvidenceContext,
    ) -> SQLExplainResponse:
        payload = program_context.to_prompt_payload()
        program = payload["program"]
        metadata = payload["metadata"]
        lineage = payload["lineage"]

        read_tables = list(program["read_tables"])
        write_targets = list(program["write_targets"])

        main_tables: list[dict[str, Any]] = []
        if metadata["available"]:
            for item in metadata["tables"]:
                main_tables.append(
                    {
                        "role": item["role"],
                        "table": (
                            item["canonical_table"]
                            or item["requested_table"]
                        ),
                        "requested_table": item["requested_table"],
                        "resolution_status": item["status"],
                        "description": item["description"],
                    }
                )
        else:
            main_tables.extend(
                {
                    "role": "read_source",
                    "table": table,
                    "resolution_status": "not_requested",
                }
                for table in read_tables
            )
            main_tables.extend(
                {
                    "role": "write_target",
                    "table": target["table"],
                    "resolution_status": "not_requested",
                }
                for target in write_targets
            )

        output_columns = [
            {
                "target": item["target"],
                "statement_index": item["statement_index"],
                "projection_index": item["projection_index"],
                "expression_sql": item["expression_sql"],
                "derived_status": item["derived_status"],
                "derived_upstream": item["derived_upstream"],
                "declared_upstream": item["declared_upstream"],
                "lineage_diff": item["diff"],
            }
            for item in lineage["columns"]
        ]

        cte_steps = [
            {
                "name": item["name"],
                "statement_index": item["statement_index"],
                "dependencies": item["dependencies"],
            }
            for item in program["ctes"]
        ]

        cte_dependencies = [
            {
                "cte": item["name"],
                "depends_on": dependency,
            }
            for item in program["ctes"]
            for dependency in item["dependencies"]
        ]

        suspicious_points: list[dict[str, Any]] = []

        for item in metadata["tables"]:
            if item["status"] != "resolved":
                suspicious_points.append(
                    {
                        "type": "metadata_resolution",
                        "table": item["requested_table"],
                        "status": item["status"],
                        "candidates": item["candidates"],
                        "message": item["error_message"],
                    }
                )

        for item in lineage["columns"]:
            if item["diff"] not in {"match", "not_comparable"}:
                suspicious_points.append(
                    {
                        "type": "lineage_diff",
                        "target": item["target"],
                        "diff": item["diff"],
                        "declared_upstream": item["declared_upstream"],
                        "derived_upstream": item["derived_upstream"],
                    }
                )

        uncertainties = [
            item.message
            for item in program_context.diagnostics
        ]

        if not metadata["available"]:
            uncertainties.append(
                "Authoritative physical metadata was not supplied; table and column semantics are structural only."
            )

        if not lineage["available"]:
            uncertainties.append(
                "Physical target-column lineage is unavailable or was intentionally degraded."
            )

        summary = (
            f"Production SQL program: {program_context.statement_count} statement(s), "
            f"{program_context.cte_count} CTE(s), {program_context.scope_count} scope(s), "
            f"{len(read_tables)} physical read table(s), "
            f"{len(write_targets)} write target(s), "
            f"{len(program_context.hints)} optimizer hint(s)."
        )

        evidence = [
            {
                "type": "program_summary",
                "source": "ProgramAnalysisService",
                "statement_count": program_context.statement_count,
                "cte_count": program_context.cte_count,
                "scope_count": program_context.scope_count,
            },
            {
                "type": "optimizer_hints",
                "source": "OptimizerHintEvidenceExtractor",
                "items": payload["optimizer_hints"],
            },
            {
                "type": "metadata",
                "source": "ProgramMetadataResolver",
                "available": metadata["available"],
            },
            {
                "type": "lineage",
                "source": "LineageEvidenceResolver",
                "available": lineage["available"],
                "total_columns": lineage["total_columns"],
                "truncated": lineage["truncated"],
            },
        ]

        return SQLExplainResponse(
            success=True,
            file_path=context.file_path,
            trace_id=context.trace_id,
            sql_summary=summary,
            business_purpose=None,
            main_tables=main_tables,
            output_columns=output_columns,
            cte_steps=cte_steps,
            cte_dependencies=cte_dependencies,
            suspicious_points=suspicious_points,
            uncertainties=uncertainties,
            route_signals={
                "need_metadata": not metadata["available"],
                "need_rag": False,
                "need_review": True,
                "need_human_confirm": any(
                    item.get("type") == "lineage_diff"
                    for item in suspicious_points
                ),
                "can_auto_fix": False,
                "next_node": "review_agent",
            },
            evidence=evidence,
            raw_output=None,
        )

    @staticmethod
    def _merge_llm_enrichment(
        *,
        deterministic: SQLExplainResponse,
        payload: dict[str, Any],
    ) -> SQLExplainResponse:
        llm_uncertainties = [
            str(item)
            for item in (payload.get("uncertainties") or [])
            if str(item).strip()
        ]

        llm_suspicious = [
            item
            for item in (payload.get("suspicious_points") or [])
            if isinstance(item, dict)
        ]

        return SQLExplainResponse(
            success=True,
            file_path=deterministic.file_path,
            trace_id=deterministic.trace_id,
            sql_summary=(
                str(payload.get("sql_summary") or "").strip()
                or deterministic.sql_summary
            ),
            business_purpose=(
                payload.get("business_purpose")
                if payload.get("business_purpose") is not None
                else deterministic.business_purpose
            ),
            # Deterministic structural facts are authoritative.
            main_tables=deterministic.main_tables,
            output_columns=deterministic.output_columns,
            cte_steps=deterministic.cte_steps,
            cte_dependencies=deterministic.cte_dependencies,
            suspicious_points=(
                deterministic.suspicious_points
                + llm_suspicious
            ),
            uncertainties=list(
                dict.fromkeys(
                    deterministic.uncertainties
                    + llm_uncertainties
                )
            ),
            route_signals=deterministic.route_signals,
            evidence=deterministic.evidence,
            raw_output=payload,
        )
