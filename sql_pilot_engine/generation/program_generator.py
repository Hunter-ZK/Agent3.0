from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlglot import exp

from sql_pilot_engine.analysis.sql_parser import SQLParser
from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.generation.program_plan import (
    ProgramCTEPlan,
    ProgramPlan,
    ProgramStatementPlan,
)
from sql_pilot_engine.llm.protocols import StructuredGenerationModel
from sql_pilot_engine.program.enums import SourceBindingKind
from sql_pilot_engine.program.service import ProgramAnalysisService
from sql_pilot_engine.services.review_service import ReviewService
from sql_pilot_engine.spec.models import FixedReportSpec, FixedReportWriteTarget


PROGRAM_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_index": {"type": "integer"},
                    "purpose": {"type": "string"},
                    "ctes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "purpose": {"type": "string"},
                                "dependencies": {"type": "array"},
                                "source_tables": {"type": "array"},
                                "output_columns": {"type": "array"},
                            },
                            "required": [
                                "name",
                                "purpose",
                                "dependencies",
                                "source_tables",
                                "output_columns",
                            ],
                        },
                    },
                    "final_select_purpose": {"type": "string"},
                    "final_dependencies": {"type": "array"},
                },
                "required": [
                    "target_index",
                    "purpose",
                    "ctes",
                    "final_select_purpose",
                    "final_dependencies",
                ],
            },
        },
        "assumptions": {"type": "array"},
    },
    "required": ["statements", "assumptions"],
}


STAGE_SQL_SCHEMA = {
    "type": "object",
    "properties": {
        "select_sql": {"type": "string"},
        "assumptions": {"type": "array"},
    },
    "required": ["select_sql", "assumptions"],
}


PLAN_SYSTEM_PROMPT = """
你是生产级 MaxCompute SQL Program Planner。

输入是 FixedReportSpec。你只负责把需求拆成 ProgramPlan，不直接生成 SQL。

必须遵守：
- 一个 write target 对应一个 statement plan；
- target_index 只能引用 Spec 中现有 write target；
- CTE 必须组成无环 DAG；
- source_tables 只能来自 Spec.source_tables；
- final_dependencies 只能引用当前 statement 的 CTE；
- 不创造新的物理源表、写入目标、字段或业务口径；
- 复杂需求应拆成多个职责单一的 CTE，而不是设计一个巨型 SELECT；
- 不确定的业务口径放入 assumptions，不要猜。

只返回 JSON。
""".strip()


STAGE_SYSTEM_PROMPT = """
你是生产级 MaxCompute SQL staged generator。

你只生成一个 SELECT / query body，不生成 INSERT、CREATE、DROP、SET。
系统会确定性地组装 CTE 名称、INSERT 目标和 PARTITION，因此你无权修改这些结构。

必须遵守：
- 只能使用当前 Stage 明确允许的物理 source_tables 和 dependency CTE；
- 不创造未声明的表或字段；
- 输出必须是一条可解析 Query；
- 不输出 Markdown；
- 不确定的业务语义写入 assumptions，不要猜。

只返回 JSON。
""".strip()


@dataclass(frozen=True, slots=True)
class ProgramGenerationResult:
    success: bool
    trusted_candidate: bool
    plan: ProgramPlan | None
    candidate_sql: str | None
    diagnostics: tuple[str, ...] = ()
    review_issues: tuple[dict[str, Any], ...] = ()


class ProgramGenerationError(RuntimeError):
    pass


class ProductionProgramGenerator:
    """
    FixedReportSpec -> ProgramPlan -> staged SQL -> Program/Review Gate。

    与 Text-to-SQL Query Line 分离：这里生成的是完整 DataWorks / MaxCompute SQL Program。
    """

    def __init__(
        self,
        *,
        model: StructuredGenerationModel,
        review_service: ReviewService | None = None,
        parser: SQLParser | None = None,
        program_analysis: ProgramAnalysisService | None = None,
    ) -> None:
        self._model = model
        self._review_service = review_service or ReviewService()
        self._parser = parser or SQLParser()
        self._program_analysis = program_analysis or ProgramAnalysisService()

    def generate(
        self,
        *,
        spec: FixedReportSpec,
        dialect: str = "maxcompute",
        metadata_provider=None,
    ) -> ProgramGenerationResult:
        try:
            plan = self._plan(spec)
            self._validate_plan_against_spec(plan=plan, spec=spec)
            candidate = self._generate_program(
                spec=spec,
                plan=plan,
                dialect=dialect,
            )
            return self._gate_candidate(
                spec=spec,
                plan=plan,
                candidate_sql=candidate,
                dialect=dialect,
                metadata_provider=metadata_provider,
            )
        except ProgramGenerationError as exc:
            return ProgramGenerationResult(
                success=False,
                trusted_candidate=False,
                plan=None,
                candidate_sql=None,
                diagnostics=(str(exc),),
            )

    def _plan(self, spec: FixedReportSpec) -> ProgramPlan:
        raw = self._model.generate_json(
            system_prompt=PLAN_SYSTEM_PROMPT,
            user_prompt=(
                "请基于以下 FixedReportSpec 生成 ProgramPlan：\n"
                + json.dumps(
                    spec.to_prompt_payload(),
                    ensure_ascii=False,
                    indent=2,
                )
            ),
            json_schema=PROGRAM_PLAN_SCHEMA,
        )
        return self._parse_plan(raw)

    @staticmethod
    def _parse_plan(raw: dict[str, Any]) -> ProgramPlan:
        if not isinstance(raw, dict):
            raise ProgramGenerationError(
                "Program Planner must return a JSON object."
            )
        if not isinstance(raw.get("statements"), list):
            raise ProgramGenerationError(
                "ProgramPlan.statements must be an array."
            )

        statements: list[ProgramStatementPlan] = []
        try:
            for raw_statement in raw["statements"]:
                ctes = tuple(
                    ProgramCTEPlan(
                        name=str(item["name"]),
                        purpose=str(item["purpose"]),
                        dependencies=tuple(
                            str(value)
                            for value in (item.get("dependencies") or [])
                        ),
                        source_tables=tuple(
                            str(value)
                            for value in (item.get("source_tables") or [])
                        ),
                        output_columns=tuple(
                            str(value)
                            for value in (item.get("output_columns") or [])
                        ),
                    )
                    for item in (raw_statement.get("ctes") or [])
                )
                statements.append(
                    ProgramStatementPlan(
                        target_index=int(raw_statement["target_index"]),
                        purpose=str(raw_statement["purpose"]),
                        ctes=ctes,
                        final_select_purpose=str(
                            raw_statement["final_select_purpose"]
                        ),
                        final_dependencies=tuple(
                            str(value)
                            for value in (
                                raw_statement.get("final_dependencies") or []
                            )
                        ),
                    )
                )

            return ProgramPlan(
                statements=tuple(statements),
                assumptions=tuple(
                    str(item)
                    for item in (raw.get("assumptions") or [])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProgramGenerationError(
                f"Invalid ProgramPlan payload: {exc}"
            ) from exc

    @staticmethod
    def _validate_plan_against_spec(
        *,
        plan: ProgramPlan,
        spec: FixedReportSpec,
    ) -> None:
        expected_indexes = set(range(len(spec.write_targets)))
        actual_indexes = {
            statement.target_index
            for statement in plan.statements
        }
        if actual_indexes != expected_indexes:
            raise ProgramGenerationError(
                "ProgramPlan must contain exactly one statement per write target. "
                f"expected={sorted(expected_indexes)!r}, "
                f"actual={sorted(actual_indexes)!r}."
            )

        allowed_sources = set(spec.source_tables)
        for statement in plan.statements:
            for cte in statement.ctes:
                unexpected = set(cte.source_tables) - allowed_sources
                if unexpected:
                    raise ProgramGenerationError(
                        f"CTE {cte.name!r} planned undeclared physical sources: "
                        f"{sorted(unexpected)!r}."
                    )

    def _generate_program(
        self,
        *,
        spec: FixedReportSpec,
        plan: ProgramPlan,
        dialect: str,
    ) -> str:
        chunks: list[str] = []

        for name, value in spec.session_settings:
            chunks.append(f"SET {name}={value};")

        for statement_plan in sorted(
            plan.statements,
            key=lambda item: item.target_index,
        ):
            target = spec.write_targets[statement_plan.target_index]
            chunks.append(
                self._generate_statement(
                    spec=spec,
                    plan=statement_plan,
                    target=target,
                    dialect=dialect,
                )
            )

        return "\n\n".join(chunks).strip()

    def _generate_statement(
        self,
        *,
        spec: FixedReportSpec,
        plan: ProgramStatementPlan,
        target: FixedReportWriteTarget,
        dialect: str,
    ) -> str:
        generated_ctes: dict[str, str] = {}
        stage_assumptions: list[str] = []

        for cte in plan.topological_ctes():
            dependency_sql = {
                name: generated_ctes[name]
                for name in cte.dependencies
            }
            payload = self._generate_stage_query(
                spec=spec,
                statement_plan=plan,
                stage={
                    "kind": "cte",
                    "name": cte.name,
                    "purpose": cte.purpose,
                    "source_tables": list(cte.source_tables),
                    "dependency_ctes": list(cte.dependencies),
                    "output_columns": list(cte.output_columns),
                },
                dependency_sql=dependency_sql,
                dialect=dialect,
            )
            generated_ctes[cte.name] = payload["select_sql"]
            stage_assumptions.extend(payload["assumptions"])

        final_dependency_sql = {
            name: generated_ctes[name]
            for name in plan.final_dependencies
        }
        final_payload = self._generate_stage_query(
            spec=spec,
            statement_plan=plan,
            stage={
                "kind": "final_select",
                "purpose": plan.final_select_purpose,
                "dependency_ctes": list(plan.final_dependencies),
                "required_output_columns": [
                    field.name
                    for field in target.fields
                ] + [
                    item.name
                    for item in target.partitions
                    if item.is_dynamic
                ],
            },
            dependency_sql=final_dependency_sql,
            dialect=dialect,
        )
        stage_assumptions.extend(final_payload["assumptions"])

        with_clause = ""
        if generated_ctes:
            cte_parts = [
                f"{name} AS (\n{sql}\n)"
                for name, sql in generated_ctes.items()
            ]
            with_clause = "WITH\n" + ",\n".join(cte_parts) + "\n"

        partition_clause = self._partition_clause(target)
        insert = (
            f"INSERT OVERWRITE TABLE {target.table_name}"
            f"{partition_clause}\n"
        )

        return (
            with_clause
            + insert
            + final_payload["select_sql"].rstrip("; \n")
            + "\n;"
        )

    def _generate_stage_query(
        self,
        *,
        spec: FixedReportSpec,
        statement_plan: ProgramStatementPlan,
        stage: dict[str, Any],
        dependency_sql: dict[str, str],
        dialect: str,
    ) -> dict[str, Any]:
        prompt_payload = {
            "dialect": dialect,
            "report": {
                "name": spec.report_name,
                "business_requirement": spec.business_requirement,
                "parameters": list(spec.parameters),
                "constraints": list(spec.constraints),
            },
            "statement_purpose": statement_plan.purpose,
            "stage": stage,
            "dependency_sql": dependency_sql,
        }

        raw = self._model.generate_json(
            system_prompt=STAGE_SYSTEM_PROMPT,
            user_prompt=(
                "请生成当前 Stage 的 SELECT/query body：\n"
                + json.dumps(
                    prompt_payload,
                    ensure_ascii=False,
                    indent=2,
                )
            ),
            json_schema=STAGE_SQL_SCHEMA,
        )

        if not isinstance(raw, dict):
            raise ProgramGenerationError(
                "Stage generator must return a JSON object."
            )
        select_sql = str(raw.get("select_sql") or "").strip()
        if not select_sql:
            raise ProgramGenerationError(
                "Stage generator returned empty select_sql."
            )
        self._validate_query_body(select_sql, dialect=dialect)

        assumptions = raw.get("assumptions") or []
        if not isinstance(assumptions, list):
            raise ProgramGenerationError(
                "Stage assumptions must be an array."
            )

        return {
            "select_sql": select_sql,
            "assumptions": [str(item) for item in assumptions],
        }

    def _validate_query_body(
        self,
        sql: str,
        *,
        dialect: str,
    ) -> None:
        parsed = self._parser.parse(sql, dialect=dialect)
        if not parsed.success or parsed.statement_count != 1:
            raise ProgramGenerationError(
                "Generated stage is not one valid query: "
                f"{parsed.error_message or 'unknown parse failure'}"
            )
        if not isinstance(parsed.first_statement, exp.Query):
            raise ProgramGenerationError(
                "Generated stage must be a SELECT/query body; DML/DDL is forbidden."
            )

    @staticmethod
    def _partition_clause(target: FixedReportWriteTarget) -> str:
        if not target.partitions:
            return ""

        items = []
        for partition in target.partitions:
            if partition.is_dynamic:
                items.append(partition.name)
            else:
                items.append(
                    f"{partition.name}={partition.value}"
                )
        return " PARTITION (" + ", ".join(items) + ")"

    def _gate_candidate(
        self,
        *,
        spec: FixedReportSpec,
        plan: ProgramPlan,
        candidate_sql: str,
        dialect: str,
        metadata_provider,
    ) -> ProgramGenerationResult:
        analysis = self._program_analysis.analyze(
            candidate_sql,
            dialect=dialect,
        )
        if analysis.program is None:
            return ProgramGenerationResult(
                success=False,
                trusted_candidate=False,
                plan=plan,
                candidate_sql=candidate_sql,
                diagnostics=(
                    "Generated Program failed Program Analysis: "
                    + (analysis.failure_reason or "unknown failure"),
                ),
            )

        program = analysis.program
        if len(program.statements) != len(spec.write_targets):
            return ProgramGenerationResult(
                success=False,
                trusted_candidate=False,
                plan=plan,
                candidate_sql=candidate_sql,
                diagnostics=(
                    "Generated Program statement count does not match FixedReportSpec.",
                ),
            )

        expected_targets = tuple(
            item.table_name
            for item in spec.write_targets
        )
        actual_targets = tuple(
            statement.write_target.table_name
            if statement.write_target is not None
            else None
            for statement in program.statements
        )
        if actual_targets != expected_targets:
            return ProgramGenerationResult(
                success=False,
                trusted_candidate=False,
                plan=plan,
                candidate_sql=candidate_sql,
                diagnostics=(
                    "Generated Program write targets differ from FixedReportSpec: "
                    f"expected={expected_targets!r}, actual={actual_targets!r}.",
                ),
            )

        physical_reads = {
            binding.physical_table
            for scope in program.scope_analyses
            for binding in scope.source_bindings
            if (
                binding.kind is SourceBindingKind.PHYSICAL_TABLE
                and binding.physical_table is not None
            )
        }
        unexpected_reads = physical_reads - set(spec.source_tables)
        if unexpected_reads:
            return ProgramGenerationResult(
                success=False,
                trusted_candidate=False,
                plan=plan,
                candidate_sql=candidate_sql,
                diagnostics=(
                    "Generated Program used undeclared physical source tables: "
                    f"{sorted(unexpected_reads)!r}.",
                ),
            )

        review_issues: list[dict[str, Any]] = []
        blocking = False
        for statement in program.statements:
            review = self._review_service.review(
                SQLExecutionContext(
                    sql=statement.normalized_sql,
                    dialect=dialect,
                    metadata_provider=metadata_provider,
                    enable_metadata=(metadata_provider is not None),
                )
            )
            review_issues.extend(
                item.to_dict()
                for item in review.issues
            )
            if any(item.blocking for item in review.issues):
                blocking = True

        diagnostics = tuple(
            plan.assumptions
        )

        return ProgramGenerationResult(
            success=True,
            trusted_candidate=not blocking,
            plan=plan,
            candidate_sql=candidate_sql,
            diagnostics=diagnostics,
            review_issues=tuple(review_issues),
        )
