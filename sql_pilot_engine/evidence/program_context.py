from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sql_pilot_engine.evidence.hints import (
    OptimizerHintEvidence,
    OptimizerHintEvidenceExtractor,
)
from sql_pilot_engine.evidence.lineage import (
    LineageEvidenceError,
    ProgramLineageEvidence,
)
from sql_pilot_engine.evidence.lineage_resolver import (
    LineageEvidenceResolver,
)
from sql_pilot_engine.evidence.program_metadata import (
    ProgramMetadataEvidence,
    ProgramMetadataResolver,
)
from sql_pilot_engine.metadata.catalog import MetadataCatalog
from sql_pilot_engine.metadata.provider import MetadataProvider
from sql_pilot_engine.program.enums import SourceBindingKind
from sql_pilot_engine.program.models import SQLProgram
from sql_pilot_engine.program.service import ProgramAnalysisService


@dataclass(frozen=True, slots=True)
class ProgramEvidenceDiagnostic:
    """Production Program Context 构建过程中的显式降级事实。"""

    code: str
    message: str
    capability: str
    severity: str = "warning"


@dataclass(frozen=True, slots=True)
class ProgramEvidenceContext:
    """
    Production SQL capability 的共享确定性上下文。

    它只聚合已经存在的稳定事实：
        SQLProgram
        ProgramMetadataEvidence
        ProgramLineageEvidence
        OptimizerHintEvidence

    不产生 Review verdict，也不让 LLM 回写这些事实。
    """

    program: SQLProgram
    hints: tuple[OptimizerHintEvidence, ...]
    metadata: ProgramMetadataEvidence | None = None
    lineage: ProgramLineageEvidence | None = None
    diagnostics: tuple[ProgramEvidenceDiagnostic, ...] = ()

    @property
    def statement_count(self) -> int:
        return len(self.program.statements)

    @property
    def cte_count(self) -> int:
        return len(self.program.cte_nodes)

    @property
    def scope_count(self) -> int:
        return len(self.program.scope_analyses)

    def to_prompt_payload(
        self,
        *,
        max_lineage_columns: int = 200,
    ) -> dict[str, Any]:
        """投影为 LLM 可消费、可序列化、带来源边界的结构化上下文。"""

        scope_name_by_id = {
            scope.scope_id: (scope.cte_name or scope.scope_id)
            for scope in self.program.scope_analyses
        }

        read_tables = sorted(
            {
                binding.physical_table
                for scope in self.program.scope_analyses
                for binding in scope.source_bindings
                if (
                    binding.kind is SourceBindingKind.PHYSICAL_TABLE
                    and binding.physical_table is not None
                )
            }
        )

        statements: list[dict[str, Any]] = []
        write_targets: list[dict[str, Any]] = []

        for statement in self.program.statements:
            target = statement.write_target
            target_payload: dict[str, Any] | None = None

            if target is not None:
                target_payload = {
                    "table": target.table_name,
                    "strategy": target.strategy.value,
                    "partitions": [
                        {
                            "name": item.name,
                            "value": item.value,
                            "dynamic": item.is_dynamic,
                        }
                        for item in target.partition_spec
                    ],
                }
                write_targets.append(target_payload)

            statements.append(
                {
                    "index": statement.index,
                    "kind": statement.kind.value,
                    "cte_names": list(statement.cte_names),
                    "write_target": target_payload,
                }
            )

        ctes = [
            {
                "name": node.name,
                "statement_index": node.statement_index,
                "scope_id": node.scope_id,
                "dependencies": [
                    scope_name_by_id.get(dep, dep)
                    for dep in node.dependency_scope_ids
                ],
            }
            for node in self.program.cte_nodes
        ]

        metadata_tables: list[dict[str, Any]] = []
        metadata_columns_summary: dict[str, int] = {}
        if self.metadata is not None:
            for item in self.metadata.tables:
                table_description = None
                if item.metadata is not None:
                    table_description = item.metadata.business.description

                metadata_tables.append(
                    {
                        "role": item.role.value,
                        "requested_table": item.requested_table,
                        "status": item.status.value,
                        "canonical_table": item.canonical_table,
                        "candidates": list(item.candidates),
                        "description": table_description,
                        "error_message": item.error_message,
                    }
                )

            for item in self.metadata.columns:
                key = item.status.value
                metadata_columns_summary[key] = (
                    metadata_columns_summary.get(key, 0) + 1
                )

        lineage_columns: list[dict[str, Any]] = []
        lineage_truncated = False
        if self.lineage is not None:
            selected = self.lineage.columns[:max_lineage_columns]
            lineage_truncated = len(self.lineage.columns) > len(selected)
            for item in selected:
                lineage_columns.append(
                    {
                        "target": (
                            f"{item.target.table_full_name}.{item.target.column_name}"
                        ),
                        "statement_index": item.statement_index,
                        "projection_index": item.projection_index,
                        "expression_sql": item.expression_sql,
                        "derived_status": item.derived_status.value,
                        "derived_upstream": [
                            f"{ref.table_full_name}.{ref.column_name}"
                            for ref in item.derived_upstream
                        ],
                        "declared_upstream": [
                            f"{ref.table_full_name}.{ref.column_name}"
                            for ref in item.declared_upstream
                        ],
                        "diff": item.diff.kind.value,
                        "unresolved_sources": list(item.unresolved_sources),
                        "error_message": item.error_message,
                    }
                )

        return {
            "program": {
                "statement_count": self.statement_count,
                "cte_count": self.cte_count,
                "scope_count": self.scope_count,
                "parameter_names": sorted(
                    {item.name for item in self.program.parameter_bindings}
                ),
                "session_hints": [
                    {
                        "name": item.name,
                        "value": item.value,
                    }
                    for item in self.program.session_hints
                ],
                "statements": statements,
                "read_tables": read_tables,
                "write_targets": write_targets,
                "ctes": ctes,
            },
            "optimizer_hints": [
                {
                    "name": item.name,
                    "arguments": list(item.arguments),
                    "statement_index": item.statement_index,
                    "scope_id": item.scope_id,
                }
                for item in self.hints
            ],
            "metadata": {
                "available": self.metadata is not None,
                "tables": metadata_tables,
                "column_resolution_summary": metadata_columns_summary,
            },
            "lineage": {
                "available": self.lineage is not None,
                "columns": lineage_columns,
                "truncated": lineage_truncated,
                "total_columns": (
                    len(self.lineage.columns)
                    if self.lineage is not None
                    else 0
                ),
            },
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "capability": item.capability,
                    "severity": item.severity,
                }
                for item in self.diagnostics
            ],
        }

    def render_for_llm(self) -> str:
        return json.dumps(
            self.to_prompt_payload(),
            ensure_ascii=False,
            indent=2,
        )


class ProgramEvidenceContextError(RuntimeError):
    pass


class ProgramEvidenceContextBuilder:
    """
    Raw production SQL -> Program + deterministic Evidence Context。

    Metadata / Lineage 是可降级增强：
    - Program Analysis 失败：整体失败；
    - Hint 提取失败：整体失败，因为它依赖 Program/SourceMap 内部一致性；
    - Metadata 不可用：保留 Program + Hint；
    - Lineage 前置条件不足：记录 diagnostic，不让 Explain 等消费者整体失败。
    """

    def __init__(
        self,
        *,
        analysis_service: ProgramAnalysisService | None = None,
        hint_extractor: OptimizerHintEvidenceExtractor | None = None,
        lineage_resolver: LineageEvidenceResolver | None = None,
    ) -> None:
        self._analysis_service = analysis_service or ProgramAnalysisService()
        self._hint_extractor = hint_extractor or OptimizerHintEvidenceExtractor()
        self._lineage_resolver = lineage_resolver or LineageEvidenceResolver()

    def build(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
        metadata_provider: MetadataProvider | None = None,
        metadata_catalog: MetadataCatalog | None = None,
    ) -> ProgramEvidenceContext:
        result = self._analysis_service.analyze(sql, dialect=dialect)
        if result.program is None:
            raise ProgramEvidenceContextError(
                result.failure_reason or "Program analysis failed."
            )

        program = result.program
        diagnostics: list[ProgramEvidenceDiagnostic] = [
            ProgramEvidenceDiagnostic(
                code="program_analysis_diagnostic",
                message=message,
                capability="program",
            )
            for message in result.diagnostics
        ]

        hints = self._hint_extractor.extract(program)

        metadata_evidence: ProgramMetadataEvidence | None = None
        lineage_evidence: ProgramLineageEvidence | None = None

        if metadata_provider is not None:
            catalog = metadata_catalog or self._catalog_from_provider(
                metadata_provider
            )

            if catalog is None:
                diagnostics.append(
                    ProgramEvidenceDiagnostic(
                        code="metadata_catalog_unavailable",
                        message=(
                            "Metadata provider does not expose the catalog "
                            "operations required for authoritative identifier resolution."
                        ),
                        capability="metadata",
                    )
                )
            else:
                metadata_evidence = ProgramMetadataResolver(
                    provider=metadata_provider,
                    catalog=catalog,
                ).resolve(program)

                try:
                    lineage_evidence = self._lineage_resolver.resolve(
                        program,
                        metadata_evidence,
                        dialect=dialect,
                    )
                except LineageEvidenceError as exc:
                    diagnostics.append(
                        ProgramEvidenceDiagnostic(
                            code="lineage_unavailable",
                            message=str(exc),
                            capability="lineage",
                        )
                    )

        return ProgramEvidenceContext(
            program=program,
            hints=hints,
            metadata=metadata_evidence,
            lineage=lineage_evidence,
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def _catalog_from_provider(
        provider: MetadataProvider,
    ) -> MetadataCatalog | None:
        required = (
            "find_tables",
            "find_table_identifiers",
            "find_columns",
            "find_column_usages",
        )
        if all(callable(getattr(provider, name, None)) for name in required):
            return provider  # type: ignore[return-value]
        return None
