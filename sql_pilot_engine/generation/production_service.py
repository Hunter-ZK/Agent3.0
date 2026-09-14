from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sql_pilot_engine.evidence.program_context import (
    ProgramEvidenceContextBuilder,
    ProgramEvidenceContextError,
)
from sql_pilot_engine.generation.program_generator import (
    ProductionProgramGenerator,
    ProgramGenerationResult,
)
from sql_pilot_engine.llm.protocols import StructuredGenerationModel
from sql_pilot_engine.metadata.models import MetadataLookupStatus, TableMetadata
from sql_pilot_engine.metadata.provider import MetadataProvider
from sql_pilot_engine.services.review_service import ReviewService
from sql_pilot_engine.spec.models import FixedReportSpec


@dataclass(frozen=True, slots=True)
class GenerationMetadataContext:
    available: bool
    tables: tuple[dict[str, Any], ...]
    diagnostics: tuple[str, ...] = ()

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "tables": list(self.tables),
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True, slots=True)
class ProductionGenerateResult:
    success: bool
    trusted_candidate: bool
    candidate_sql: str | None
    plan: Any | None
    diagnostics: tuple[str, ...]
    review_issues: tuple[dict[str, Any], ...]
    metadata_context: GenerationMetadataContext
    validation: dict[str, Any]
    evidence_summary: dict[str, Any]


class _MetadataGroundedModel:
    def __init__(
        self,
        *,
        model: StructuredGenerationModel,
        metadata_context: GenerationMetadataContext,
    ) -> None:
        self._model = model
        self._metadata_context = metadata_context

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        import json

        metadata_text = json.dumps(
            self._metadata_context.to_prompt_payload(),
            ensure_ascii=False,
            indent=2,
        )
        grounded_system = (
            system_prompt
            + "\n\n## Authoritative Metadata Rule\n"
            + "若下方 Metadata available=true，则物理表和字段事实以 Metadata 为最高优先级。"
            + "不得生成 Metadata 中不存在的物理字段；无法满足需求时写入 assumptions，不要猜。"
        )
        grounded_user = (
            user_prompt
            + "\n\n## Authoritative Generation Metadata\n```json\n"
            + metadata_text
            + "\n```"
        )
        return self._model.generate_json(
            system_prompt=grounded_system,
            user_prompt=grounded_user,
            json_schema=json_schema,
        )


class ProductionGenerateService:
    """
    生产级 Program Generate 门面。

    FixedReportSpec 仍是“业务要求/目标表/字段/分区”的稳定输入契约；本服务把权威 Metadata
    前置注入 Planner / staged generator，并在 Candidate 完成后重新构建 Program/Evidence。

    没有 Metadata 时仍可产生 draft candidate，但默认不能标记为 production-trusted。
    """

    def __init__(
        self,
        *,
        model: StructuredGenerationModel,
        review_service: ReviewService | None = None,
        evidence_builder: ProgramEvidenceContextBuilder | None = None,
        require_metadata_for_trust: bool = True,
    ) -> None:
        self._model = model
        self._review_service = review_service or ReviewService()
        self._evidence_builder = evidence_builder or ProgramEvidenceContextBuilder()
        self._require_metadata_for_trust = require_metadata_for_trust

    def generate(
        self,
        *,
        spec: FixedReportSpec,
        dialect: str = "maxcompute",
        metadata_provider: MetadataProvider | None = None,
    ) -> ProductionGenerateResult:
        metadata_context = self._build_metadata_context(
            spec=spec,
            metadata_provider=metadata_provider,
        )

        source_errors = [
            item
            for item in metadata_context.tables
            if item["role"] == "read_source" and item["status"] != "found"
        ]
        if metadata_provider is not None and source_errors:
            return ProductionGenerateResult(
                success=False,
                trusted_candidate=False,
                candidate_sql=None,
                plan=None,
                diagnostics=(
                    *metadata_context.diagnostics,
                    "Authoritative source Metadata is incomplete; production generation stopped before LLM planning.",
                ),
                review_issues=(),
                metadata_context=metadata_context,
                validation={
                    "metadata_grounding": "failed",
                    "program_gate": "not_run",
                    "lineage_gate": "not_run",
                },
                evidence_summary={},
            )

        grounded_model = _MetadataGroundedModel(
            model=self._model,
            metadata_context=metadata_context,
        )
        base_result = ProductionProgramGenerator(
            model=grounded_model,
            review_service=self._review_service,
        ).generate(
            spec=spec,
            dialect=dialect,
            metadata_provider=metadata_provider,
        )

        return self._finalize(
            spec=spec,
            dialect=dialect,
            metadata_provider=metadata_provider,
            metadata_context=metadata_context,
            base_result=base_result,
        )

    def _finalize(
        self,
        *,
        spec: FixedReportSpec,
        dialect: str,
        metadata_provider: MetadataProvider | None,
        metadata_context: GenerationMetadataContext,
        base_result: ProgramGenerationResult,
    ) -> ProductionGenerateResult:
        diagnostics = list(base_result.diagnostics)
        validation: dict[str, Any] = {
            "metadata_grounding": (
                "passed" if metadata_provider is not None else "not_configured"
            ),
            "program_gate": "passed" if base_result.success else "failed",
            "review_gate": (
                "passed" if base_result.trusted_candidate else "blocked"
            ),
            "lineage_gate": "not_run",
        }
        evidence_summary: dict[str, Any] = {}
        trusted = base_result.trusted_candidate

        if base_result.candidate_sql is None:
            return ProductionGenerateResult(
                success=base_result.success,
                trusted_candidate=False,
                candidate_sql=None,
                plan=base_result.plan,
                diagnostics=tuple(diagnostics),
                review_issues=base_result.review_issues,
                metadata_context=metadata_context,
                validation=validation,
                evidence_summary=evidence_summary,
            )

        if metadata_provider is None:
            if self._require_metadata_for_trust:
                trusted = False
                diagnostics.append(
                    "Candidate is a draft: authoritative Metadata was not configured, so production trust is withheld."
                )
            return ProductionGenerateResult(
                success=base_result.success,
                trusted_candidate=trusted,
                candidate_sql=base_result.candidate_sql,
                plan=base_result.plan,
                diagnostics=tuple(diagnostics),
                review_issues=base_result.review_issues,
                metadata_context=metadata_context,
                validation=validation,
                evidence_summary=evidence_summary,
            )

        try:
            evidence = self._evidence_builder.build(
                base_result.candidate_sql,
                dialect=dialect,
                metadata_provider=metadata_provider,
            )
            payload = evidence.to_prompt_payload(max_lineage_columns=500)
        except ProgramEvidenceContextError as exc:
            trusted = False
            validation["lineage_gate"] = "failed"
            diagnostics.append(f"Generated candidate Evidence Gate failed: {exc}")
            payload = None

        if payload is not None:
            table_resolutions = payload["metadata"]["tables"]
            unresolved = [
                item
                for item in table_resolutions
                if item["status"] != "resolved"
            ]
            lineage_available = bool(payload["lineage"]["available"])
            validation["metadata_resolution"] = (
                "passed" if not unresolved else "failed"
            )
            validation["lineage_gate"] = (
                "passed" if lineage_available else "failed"
            )
            if unresolved or not lineage_available:
                trusted = False
                if unresolved:
                    diagnostics.append(
                        "Generated candidate has unresolved Metadata identities: "
                        + ", ".join(item["requested_table"] for item in unresolved)
                    )
                if not lineage_available:
                    diagnostics.append(
                        "Generated candidate target-column Lineage could not be fully established."
                    )

            evidence_summary = {
                "statement_count": payload["program"]["statement_count"],
                "cte_count": payload["program"]["cte_count"],
                "read_tables": payload["program"]["read_tables"],
                "write_targets": payload["program"]["write_targets"],
                "metadata_resolved": not unresolved,
                "lineage_available": lineage_available,
                "lineage_column_count": payload["lineage"]["total_columns"],
            }

        target_alignment_failures = [
            item
            for item in metadata_context.tables
            if item["role"] == "write_target"
            and item.get("alignment") == "mismatch"
        ]
        if target_alignment_failures:
            trusted = False
            validation["target_schema_alignment"] = "failed"
            diagnostics.append(
                "FixedReportSpec target fields/partitions do not align with authoritative target Metadata."
            )
        else:
            validation["target_schema_alignment"] = "passed"

        return ProductionGenerateResult(
            success=base_result.success,
            trusted_candidate=trusted,
            candidate_sql=base_result.candidate_sql,
            plan=base_result.plan,
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            review_issues=base_result.review_issues,
            metadata_context=metadata_context,
            validation=validation,
            evidence_summary=evidence_summary,
        )

    @staticmethod
    def _build_metadata_context(
        *,
        spec: FixedReportSpec,
        metadata_provider: MetadataProvider | None,
    ) -> GenerationMetadataContext:
        if metadata_provider is None:
            return GenerationMetadataContext(
                available=False,
                tables=(),
                diagnostics=(
                    "Authoritative Metadata is not configured for generation.",
                ),
            )

        tables: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        targets = {item.table_name: item for item in spec.write_targets}

        for role, names in (
            ("read_source", spec.source_tables),
            ("write_target", tuple(targets)),
        ):
            for table_name in names:
                lookup = metadata_provider.get_table(table_name)
                if lookup.status is not MetadataLookupStatus.FOUND or lookup.table is None:
                    status = lookup.status.value
                    tables.append(
                        {
                            "role": role,
                            "table": table_name,
                            "status": status,
                            "error_message": lookup.error_message,
                        }
                    )
                    diagnostics.append(
                        f"Metadata {status}: {table_name}"
                    )
                    continue

                table = lookup.table
                item = ProductionGenerateService._table_payload(
                    role=role,
                    table=table,
                )
                if role == "write_target":
                    target = targets[table_name]
                    expected_fields = {
                        field.name for field in target.fields
                    }
                    expected_partitions = {
                        partition.name for partition in target.partitions
                    }
                    actual_fields = set(table.columns) - set(
                        table.technical.partition_fields
                    )
                    actual_partitions = set(table.technical.partition_fields)
                    item["alignment"] = (
                        "match"
                        if expected_fields <= actual_fields
                        and expected_partitions == actual_partitions
                        else "mismatch"
                    )
                    item["missing_target_fields"] = sorted(
                        expected_fields - actual_fields
                    )
                    item["expected_partitions"] = sorted(expected_partitions)
                    item["actual_partitions"] = sorted(actual_partitions)
                tables.append(item)

        return GenerationMetadataContext(
            available=True,
            tables=tuple(tables),
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def _table_payload(
        *,
        role: str,
        table: TableMetadata,
    ) -> dict[str, Any]:
        columns = sorted(
            table.columns.values(),
            key=lambda item: item.technical.ordinal_position,
        )
        return {
            "role": role,
            "table": table.full_name,
            "status": "found",
            "description": table.business.description,
            "purpose": table.business.purpose,
            "grain": table.business.grain,
            "business_key": list(table.business.business_key),
            "partition_fields": list(table.technical.partition_fields),
            "columns": [
                {
                    "name": column.name,
                    "data_type": column.technical.data_type,
                    "is_partition": column.technical.is_partition,
                    "description": column.business.description,
                    "definition": column.business.definition,
                    "is_dimension": column.semantic.is_dimension,
                    "is_metric": column.semantic.is_metric,
                    "metric_formula": column.semantic.metric_formula,
                    "metric_aggregation": column.semantic.metric_aggregation,
                }
                for column in columns
            ],
        }
