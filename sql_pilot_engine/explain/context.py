from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlglot import exp

from sql_pilot_engine.analysis.sql_parser import SQLParser
from sql_pilot_engine.dialects.sqlglot import resolve_sqlglot_dialect
from sql_pilot_engine.evidence.program_context import ProgramEvidenceContext
from sql_pilot_engine.program.enums import SourceBindingKind


@dataclass(frozen=True, slots=True)
class ExplainStatementContext:
    statement_index: int
    kind: str
    cte_names: tuple[str, ...]
    write_target: dict[str, Any] | None
    sql_excerpt: str

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "statement_index": self.statement_index,
            "kind": self.kind,
            "cte_names": list(self.cte_names),
            "write_target": self.write_target,
            "sql_excerpt": self.sql_excerpt,
        }


@dataclass(frozen=True, slots=True)
class ExplainCTEContext:
    statement_index: int
    name: str
    dependencies: tuple[str, ...]
    physical_sources: tuple[str, ...]
    unresolved_sources: tuple[str, ...]
    output_columns: tuple[str, ...]
    output_complete: bool
    aggregates: tuple[dict[str, Any], ...]
    predicates: tuple[dict[str, Any], ...]
    sql_excerpt: str

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "statement_index": self.statement_index,
            "name": self.name,
            "dependencies": list(self.dependencies),
            "physical_sources": list(self.physical_sources),
            "unresolved_sources": list(self.unresolved_sources),
            "output_columns": list(self.output_columns),
            "output_complete": self.output_complete,
            "aggregates": list(self.aggregates),
            "predicates": list(self.predicates),
            "sql_excerpt": self.sql_excerpt,
        }


@dataclass(frozen=True, slots=True)
class ProductionExplainContext:
    evidence: ProgramEvidenceContext
    statements: tuple[ExplainStatementContext, ...]
    ctes: tuple[ExplainCTEContext, ...]

    def compact_program_payload(self) -> dict[str, Any]:
        evidence_payload = self.evidence.to_prompt_payload(
            max_lineage_columns=160,
        )
        return {
            "program": evidence_payload["program"],
            "optimizer_hints": evidence_payload["optimizer_hints"],
            "metadata": evidence_payload["metadata"],
            "lineage": evidence_payload["lineage"],
            "diagnostics": evidence_payload["diagnostics"],
            "statements": [
                item.to_prompt_payload()
                for item in self.statements
            ],
        }


class ProductionExplainContextBuilder:
    """
    Explain 专属 Context Engineering。

    SQLProgram 保持 CLOSED；本层只消费 Program/Evidence，并补充 Explain 所需的
    statement/CTE 代码片段和局部事实。长 SQL 不再依赖一个头尾 excerpt。
    """

    def __init__(
        self,
        *,
        parser: SQLParser | None = None,
        cte_sql_limit: int = 2200,
        statement_sql_limit: int = 3600,
    ) -> None:
        self._parser = parser or SQLParser()
        self._cte_sql_limit = cte_sql_limit
        self._statement_sql_limit = statement_sql_limit

    def build(
        self,
        evidence: ProgramEvidenceContext,
        *,
        dialect: str,
    ) -> ProductionExplainContext:
        program = evidence.program
        prompt_payload = evidence.to_prompt_payload(max_lineage_columns=160)
        cte_meta = {
            (item["statement_index"], item["name"]): item
            for item in prompt_payload["program"]["ctes"]
        }
        scope_by_cte = {
            (scope.statement_index, (scope.cte_name or "").lower()): scope
            for scope in program.scope_analyses
            if scope.cte_name
        }

        cte_sql = self._extract_cte_sql(
            evidence=evidence,
            dialect=dialect,
        )

        statements: list[ExplainStatementContext] = []
        for statement_payload, statement in zip(
            prompt_payload["program"]["statements"],
            program.statements,
            strict=True,
        ):
            statements.append(
                ExplainStatementContext(
                    statement_index=statement.index,
                    kind=statement.kind.value,
                    cte_names=tuple(statement.cte_names),
                    write_target=statement_payload["write_target"],
                    sql_excerpt=self._bounded_excerpt(
                        statement.normalized_sql,
                        limit=self._statement_sql_limit,
                    ),
                )
            )

        ctes: list[ExplainCTEContext] = []
        for node in program.cte_nodes:
            key = (node.statement_index, node.name.lower())
            scope = scope_by_cte.get(key)
            meta = cte_meta.get(key, {})

            physical_sources: set[str] = set()
            unresolved_sources: set[str] = set()
            output_columns: tuple[str, ...] = ()
            output_complete = False
            aggregates: tuple[dict[str, Any], ...] = ()
            predicates: tuple[dict[str, Any], ...] = ()

            if scope is not None:
                for binding in scope.source_bindings:
                    if (
                        binding.kind is SourceBindingKind.PHYSICAL_TABLE
                        and binding.physical_table
                    ):
                        physical_sources.add(binding.physical_table)
                    elif binding.kind is SourceBindingKind.UNRESOLVED:
                        unresolved_sources.add(
                            binding.unresolved_reason or binding.alias
                        )

                output_columns = scope.output_projection.column_names
                output_complete = scope.output_projection.complete
                aggregates = tuple(
                    {
                        "function": item.function,
                        "column": (
                            {
                                "name": item.column.name,
                                "qualifier": item.column.qualifier,
                            }
                            if item.column is not None
                            else None
                        ),
                        "distinct": item.distinct,
                    }
                    for item in scope.facts.aggregate_facts
                )
                predicates = tuple(
                    {
                        "column": {
                            "name": item.column.name,
                            "qualifier": item.column.qualifier,
                        },
                        "operator": item.operator,
                        "values": list(item.values),
                    }
                    for item in scope.facts.predicate_facts
                )

            ctes.append(
                ExplainCTEContext(
                    statement_index=node.statement_index,
                    name=node.name,
                    dependencies=tuple(meta.get("dependencies") or ()),
                    physical_sources=tuple(sorted(physical_sources)),
                    unresolved_sources=tuple(sorted(unresolved_sources)),
                    output_columns=output_columns,
                    output_complete=output_complete,
                    aggregates=aggregates,
                    predicates=predicates,
                    sql_excerpt=self._bounded_excerpt(
                        cte_sql.get(key, ""),
                        limit=self._cte_sql_limit,
                    ),
                )
            )

        return ProductionExplainContext(
            evidence=evidence,
            statements=tuple(statements),
            ctes=tuple(ctes),
        )

    def _extract_cte_sql(
        self,
        *,
        evidence: ProgramEvidenceContext,
        dialect: str,
    ) -> dict[tuple[int, str], str]:
        result: dict[tuple[int, str], str] = {}
        render_dialect = resolve_sqlglot_dialect(dialect=dialect)

        for statement in evidence.program.statements:
            parsed = self._parser.parse(
                statement.normalized_sql,
                dialect=dialect,
            )
            if not parsed.success or parsed.first_statement is None:
                continue

            for cte in parsed.first_statement.find_all(exp.CTE):
                name = cte.alias_or_name.strip().lower()
                if not name:
                    continue
                result[(statement.index, name)] = cte.this.sql(
                    dialect=render_dialect,
                    pretty=True,
                )

        return result

    @staticmethod
    def _bounded_excerpt(
        sql: str,
        *,
        limit: int,
    ) -> str:
        normalized = sql.strip()
        if len(normalized) <= limit:
            return normalized
        half = max(1, limit // 2)
        return (
            normalized[:half]
            + "\n-- [EXPLAIN CHUNK TRUNCATED] --\n"
            + normalized[-half:]
        )
