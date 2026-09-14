from __future__ import annotations

from typing import Any

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.evidence.program_context import (
    ProgramEvidenceContext,
    ProgramEvidenceContextBuilder,
)
from sql_pilot_engine.explain.context import (
    ProductionExplainContext,
    ProductionExplainContextBuilder,
)
from sql_pilot_engine.llm.explainer import LLMExplainer
from sql_pilot_engine.llm.protocols import StructuredGenerationModel
from sql_pilot_engine.program.enums import SourceBindingKind
from sql_pilot_engine.schemas.responses import SQLExplainResponse


class ExplainService:
    """
    Production SQL Explain。

    Deterministic Program/Evidence 是主事实层；LLM 是可降级语义增强层。
    对复杂 SQL，ExplainContextBuilder 会把每个 CTE 的事实与代码片段独立分块，
    LLMExplainer 再做 CTE batch explanation + program synthesis。
    """

    def __init__(
        self,
        llm_client: StructuredGenerationModel | None = None,
        context_builder: ProgramEvidenceContextBuilder | None = None,
        explain_context_builder: ProductionExplainContextBuilder | None = None,
    ) -> None:
        self._explainer = (
            LLMExplainer(client=llm_client)
            if llm_client is not None
            else None
        )
        self._context_builder = context_builder or ProgramEvidenceContextBuilder()
        self._explain_context_builder = (
            explain_context_builder or ProductionExplainContextBuilder()
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
            explain_context = self._explain_context_builder.build(
                program_context,
                dialect=context.dialect,
            )
            deterministic = self._deterministic_response(
                context=context,
                program_context=program_context,
                explain_context=explain_context,
            )
        except Exception as error:
            return SQLExplainResponse.failed(
                file_path=context.file_path,
                trace_id=context.trace_id,
                error_message=str(error),
            )

        if self._explainer is None or not context.enable_llm:
            return deterministic

        try:
            payload = self._explainer.explain(
                context=explain_context,
            )
        except Exception as error:
            deterministic.uncertainties.append(
                f"LLM semantic enrichment failed; deterministic explanation remains valid: {error}"
            )
            deterministic.explain_quality = {
                **deterministic.explain_quality,
                "llm_enriched": False,
                "llm_error": str(error),
            }
            return deterministic

        return self._merge_llm_enrichment(
            deterministic=deterministic,
            payload=payload,
        )

    @staticmethod
    def _deterministic_response(
        *,
        context: SQLExecutionContext,
        program_context: ProgramEvidenceContext,
        explain_context: ProductionExplainContext,
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
                        "table": item["canonical_table"] or item["requested_table"],
                        "requested_table": item["requested_table"],
                        "resolution_status": item["status"],
                        "description": item["description"],
                        "business_role": None,
                        "usage_summary": None,
                        "semantic_confidence": None,
                        "semantic_uncertainties": [],
                    }
                )
        else:
            main_tables.extend(
                {
                    "role": "read_source",
                    "table": table,
                    "resolution_status": "not_requested",
                    "business_role": None,
                    "usage_summary": None,
                    "semantic_confidence": None,
                    "semantic_uncertainties": [],
                }
                for table in read_tables
            )
            main_tables.extend(
                {
                    "role": "write_target",
                    "table": target["table"],
                    "resolution_status": "not_requested",
                    "business_role": None,
                    "usage_summary": None,
                    "semantic_confidence": None,
                    "semantic_uncertainties": [],
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
                "meaning": None,
                "derivation_summary": None,
                "semantic_confidence": None,
                "semantic_uncertainties": [],
            }
            for item in lineage["columns"]
        ]

        cte_steps = [
            {
                **item.to_prompt_payload(),
                "purpose": None,
                "processing_logic": None,
                "business_semantics": None,
                "input_semantics": None,
                "output_semantics": None,
                "semantic_confidence": None,
                "semantic_uncertainties": [],
            }
            for item in explain_context.ctes
        ]

        cte_dependencies = [
            {
                "cte": item.name,
                "statement_index": item.statement_index,
                "depends_on": dependency,
            }
            for item in explain_context.ctes
            for dependency in item.dependencies
        ]

        statement_explanations = [
            {
                "statement_index": item.statement_index,
                "kind": item.kind,
                "cte_names": list(item.cte_names),
                "write_target": item.write_target,
                "purpose": None,
                "inputs": [],
                "processing_flow": [],
                "partition_behavior": None,
                "uncertainties": [],
            }
            for item in explain_context.statements
        ]

        data_flow = ExplainService._build_data_flow(
            explain_context=explain_context,
        )

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
                "Authoritative physical metadata was not supplied; business semantics are conservative structural inference only."
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
            statement_explanations=statement_explanations,
            data_flow=data_flow,
            key_transformations=[],
            suspicious_points=suspicious_points,
            uncertainties=list(dict.fromkeys(uncertainties)),
            explain_quality={
                "structural_authority": "deterministic",
                "llm_enriched": False,
                "metadata_available": metadata["available"],
                "lineage_available": lineage["available"],
                "cte_total": len(cte_steps),
                "cte_semantic_explained": 0,
                "output_total": len(output_columns),
                "output_semantic_explained": 0,
            },
            route_signals={
                "need_metadata": not metadata["available"],
                "need_rag": False,
                "need_review": True,
                "need_human_confirm": bool(suspicious_points),
                "can_auto_fix": False,
                "next_node": "review_agent",
            },
            evidence=evidence,
            raw_output=None,
        )

    @staticmethod
    def _build_data_flow(
        *,
        explain_context: ProductionExplainContext,
    ) -> list[dict[str, Any]]:
        program = explain_context.evidence.program
        scope_name_by_id = {
            scope.scope_id: (
                scope.cte_name
                if scope.cte_name
                else f"statement:{scope.statement_index}:output"
            )
            for scope in program.scope_analyses
        }
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for scope in program.scope_analyses:
            destination = scope_name_by_id[scope.scope_id]
            for binding in scope.source_bindings:
                if (
                    binding.kind is SourceBindingKind.PHYSICAL_TABLE
                    and binding.physical_table
                ):
                    source = binding.physical_table
                    kind = "physical_table"
                elif (
                    binding.kind is SourceBindingKind.SCOPE
                    and binding.source_scope_id
                ):
                    source = scope_name_by_id.get(
                        binding.source_scope_id,
                        binding.source_scope_id,
                    )
                    kind = "scope"
                else:
                    continue

                key = (source, destination, kind)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "from": source,
                        "to": destination,
                        "kind": kind,
                        "statement_index": scope.statement_index,
                    }
                )

        for statement in program.statements:
            if statement.write_target is None:
                continue
            source = f"statement:{statement.index}:output"
            target = statement.write_target.table_name
            key = (source, target, "write_target")
            if key not in seen:
                seen.add(key)
                edges.append(
                    {
                        "from": source,
                        "to": target,
                        "kind": "write_target",
                        "statement_index": statement.index,
                    }
                )
        return edges

    @staticmethod
    def _merge_llm_enrichment(
        *,
        deterministic: SQLExplainResponse,
        payload: dict[str, Any],
    ) -> SQLExplainResponse:
        cte_semantics = {
            (item["statement_index"], item["name"]): item
            for item in payload.get("cte_explanations", [])
            if isinstance(item, dict)
            and "statement_index" in item
            and "name" in item
        }
        enriched_ctes: list[dict[str, Any]] = []
        for item in deterministic.cte_steps:
            semantic = cte_semantics.get(
                (item["statement_index"], item["name"]),
                {},
            )
            enriched_ctes.append(
                {
                    **item,
                    "purpose": semantic.get("purpose"),
                    "processing_logic": semantic.get("processing_logic"),
                    "business_semantics": semantic.get("business_semantics"),
                    "input_semantics": semantic.get("input_semantics"),
                    "output_semantics": semantic.get("output_semantics"),
                    "semantic_confidence": semantic.get("confidence"),
                    "semantic_uncertainties": semantic.get("uncertainties", []),
                }
            )

        table_semantics = {
            item["table"]: item
            for item in payload.get("table_roles", [])
            if isinstance(item, dict) and item.get("table")
        }
        enriched_tables: list[dict[str, Any]] = []
        for item in deterministic.main_tables:
            semantic = table_semantics.get(item["table"], {})
            enriched_tables.append(
                {
                    **item,
                    "business_role": semantic.get("business_role"),
                    "usage_summary": semantic.get("usage_summary"),
                    "semantic_confidence": semantic.get("confidence"),
                    "semantic_uncertainties": semantic.get("uncertainties", []),
                }
            )

        output_semantics = {
            item["target"]: item
            for item in payload.get("output_column_explanations", [])
            if isinstance(item, dict) and item.get("target")
        }
        enriched_outputs: list[dict[str, Any]] = []
        for item in deterministic.output_columns:
            semantic = output_semantics.get(item["target"], {})
            enriched_outputs.append(
                {
                    **item,
                    "meaning": semantic.get("meaning"),
                    "derivation_summary": semantic.get("derivation_summary"),
                    "semantic_confidence": semantic.get("confidence"),
                    "semantic_uncertainties": semantic.get("uncertainties", []),
                }
            )

        statement_semantics = {
            item["statement_index"]: item
            for item in payload.get("statement_explanations", [])
            if isinstance(item, dict) and "statement_index" in item
        }
        enriched_statements: list[dict[str, Any]] = []
        for item in deterministic.statement_explanations:
            semantic = statement_semantics.get(item["statement_index"], {})
            enriched_statements.append(
                {
                    **item,
                    "purpose": semantic.get("purpose"),
                    "inputs": semantic.get("inputs", []),
                    "processing_flow": semantic.get("processing_flow", []),
                    "partition_behavior": semantic.get("partition_behavior"),
                    "uncertainties": semantic.get("uncertainties", []),
                }
            )

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

        route_signals = {
            **deterministic.route_signals,
            "need_review": True,
            "can_auto_fix": False,
        }
        model_route = payload.get("route_signals")
        if isinstance(model_route, dict):
            if model_route.get("need_metadata") is True:
                route_signals["need_metadata"] = True
            if model_route.get("need_human_confirm") is True:
                route_signals["need_human_confirm"] = True

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
            main_tables=enriched_tables,
            output_columns=enriched_outputs,
            cte_steps=enriched_ctes,
            cte_dependencies=deterministic.cte_dependencies,
            statement_explanations=enriched_statements,
            data_flow=deterministic.data_flow,
            key_transformations=[
                item
                for item in (payload.get("key_transformations") or [])
                if isinstance(item, dict)
            ],
            suspicious_points=deterministic.suspicious_points + llm_suspicious,
            uncertainties=list(
                dict.fromkeys(
                    deterministic.uncertainties + llm_uncertainties
                )
            ),
            explain_quality={
                **deterministic.explain_quality,
                "llm_enriched": True,
                "cte_semantic_explained": sum(
                    1 for item in enriched_ctes if item.get("purpose")
                ),
                "output_semantic_explained": sum(
                    1 for item in enriched_outputs if item.get("meaning")
                ),
            },
            route_signals=route_signals,
            evidence=deterministic.evidence,
            raw_output=payload,
        )
