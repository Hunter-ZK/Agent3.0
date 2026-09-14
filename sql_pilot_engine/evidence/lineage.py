from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlglot import exp, to_column
from sqlglot.errors import SqlglotError
from sqlglot.lineage import Node, to_node
from sqlglot.optimizer import build_scope, qualify
from sqlglot.schema import MappingSchema

from sql_pilot_engine.dialects.sqlglot import resolve_sqlglot_dialect
from sql_pilot_engine.metadata.models import PhysicalColumnRef


class DerivedLineageStatus(str, Enum):
    """SQL-derived lineage resolution status for one projection."""

    RESOLVED = "resolved"
    NO_PHYSICAL_UPSTREAM = "no_physical_upstream"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"
    ERROR = "error"


class LineageDiffKind(str, Enum):
    """Objective relationship between declared and SQL-derived lineage."""

    MATCH = "match"
    DECLARED_ONLY = "declared_only"
    DERIVED_ONLY = "derived_only"
    PATH_MISMATCH = "path_mismatch"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True, slots=True)
class LineageDiff:
    kind: LineageDiffKind
    declared_only: tuple[PhysicalColumnRef, ...] = ()
    derived_only: tuple[PhysicalColumnRef, ...] = ()


@dataclass(frozen=True, slots=True)
class ColumnLineageEvidence:
    """Lineage evidence for one target physical column."""

    target: PhysicalColumnRef
    declared_upstream: tuple[PhysicalColumnRef, ...]
    declared_status: str | None
    derived_upstream: tuple[PhysicalColumnRef, ...]
    derived_status: DerivedLineageStatus
    diff: LineageDiff
    statement_index: int
    projection_index: int | None
    expression_sql: str | None = None
    unresolved_sources: tuple[str, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ProgramLineageEvidence:
    """Column-level lineage evidence for a complete SQLProgram."""

    columns: tuple[ColumnLineageEvidence, ...]


class LineageEvidenceError(RuntimeError):
    """Raised when authoritative lineage cannot be constructed reliably."""


def build_lineage_diff(
    *,
    declared: tuple[PhysicalColumnRef, ...],
    derived: tuple[PhysicalColumnRef, ...],
    derived_status: DerivedLineageStatus,
) -> LineageDiff:
    """Compare declared and SQL-derived lineage without turning the diff into a verdict."""

    if derived_status in {
        DerivedLineageStatus.PARTIAL,
        DerivedLineageStatus.UNRESOLVED,
        DerivedLineageStatus.ERROR,
    }:
        return LineageDiff(kind=LineageDiffKind.NOT_COMPARABLE)

    declared_set = set(declared)
    derived_set = set(derived)

    declared_only = tuple(
        sorted(
            declared_set - derived_set,
            key=_column_ref_sort_key,
        )
    )
    derived_only = tuple(
        sorted(
            derived_set - declared_set,
            key=_column_ref_sort_key,
        )
    )

    if not declared_only and not derived_only:
        kind = LineageDiffKind.MATCH
    elif declared_set and not derived_set:
        kind = LineageDiffKind.DECLARED_ONLY
    elif derived_set and not declared_set:
        kind = LineageDiffKind.DERIVED_ONLY
    else:
        kind = LineageDiffKind.PATH_MISMATCH

    return LineageDiff(
        kind=kind,
        declared_only=declared_only,
        derived_only=derived_only,
    )


@dataclass(frozen=True, slots=True)
class DerivedProjectionLineage:
    """SQL-derived lineage for one SELECT projection before target-column mapping."""

    projection_index: int
    expression_sql: str
    upstream: tuple[PhysicalColumnRef, ...]
    status: DerivedLineageStatus
    unresolved_sources: tuple[str, ...] = ()
    error_message: str | None = None


class SQLGlotDerivedLineageAdapter:
    """
    Thin adapter around SQLGlot's mature scope/lineage implementation.

    The adapter resolves projection -> physical upstream columns only. It deliberately
    does not know target tables, declared lineage, review findings, or fixes.
    """

    def derive_query(
        self,
        query: exp.Query,
        *,
        schema: MappingSchema,
        dialect: str = "maxcompute",
    ) -> tuple[DerivedProjectionLineage, ...]:
        sqlglot_dialect = resolve_sqlglot_dialect(dialect)

        qualified_query = self._qualify_query(
            query=query,
            schema=schema,
            dialect=sqlglot_dialect,
        )

        scope = build_scope(qualified_query)
        if scope is None:
            raise LineageEvidenceError(
                "SQLGlot could not build a lineage scope."
            )

        return tuple(
            self._derive_projection(
                scope=scope,
                projection=projection,
                projection_index=projection_index,
                dialect=sqlglot_dialect,
            )
            for projection_index, projection in enumerate(
                scope.expression.selects
            )
        )

    @staticmethod
    def _qualify_query(
        *,
        query: exp.Query,
        schema: MappingSchema,
        dialect: str,
    ) -> exp.Query:
        try:
            qualified = qualify.qualify(
                query.copy(),
                dialect=dialect,
                schema=schema,
                expand_stars=True,
                validate_qualify_columns=True,
                identify=False,
            )
        except (SqlglotError, ValueError) as exc:
            raise LineageEvidenceError(
                "SQLGlot qualification failed: "
                f"{exc}"
            ) from exc

        if not isinstance(qualified, exp.Query):
            raise LineageEvidenceError(
                "Qualified expression is not a Query."
            )

        return qualified

    def _derive_projection(
        self,
        *,
        scope,
        projection: exp.Expression,
        projection_index: int,
        dialect: str,
    ) -> DerivedProjectionLineage:
        expression_sql = projection.sql(
            dialect=dialect,
            pretty=False,
        )

        try:
            root = to_node(
                projection_index,
                scope=scope,
                dialect=dialect,
                trim_selects=True,
            )
        except (SqlglotError, ValueError) as exc:
            return DerivedProjectionLineage(
                projection_index=projection_index,
                expression_sql=expression_sql,
                upstream=(),
                status=DerivedLineageStatus.ERROR,
                error_message=str(exc),
            )

        upstream, unresolved = self._collect_terminal_sources(
            root,
            dialect=dialect,
        )

        if upstream and unresolved:
            status = DerivedLineageStatus.PARTIAL
        elif upstream:
            status = DerivedLineageStatus.RESOLVED
        elif unresolved:
            status = DerivedLineageStatus.UNRESOLVED
        else:
            status = DerivedLineageStatus.NO_PHYSICAL_UPSTREAM

        return DerivedProjectionLineage(
            projection_index=projection_index,
            expression_sql=expression_sql,
            upstream=upstream,
            status=status,
            unresolved_sources=unresolved,
        )

    @staticmethod
    def _collect_terminal_sources(
        root: Node,
        *,
        dialect: str,
    ) -> tuple[
        tuple[PhysicalColumnRef, ...],
        tuple[str, ...],
    ]:
        physical: set[PhysicalColumnRef] = set()
        unresolved: set[str] = set()

        for node in root.walk():
            if node.downstream:
                continue

            if isinstance(node.expression, exp.Table):
                table_name = exp.table_name(
                    node.expression,
                    dialect=dialect,
                ).strip().lower()

                column = to_column(
                    node.name,
                    dialect=dialect,
                )

                physical.add(
                    PhysicalColumnRef(
                        table_full_name=table_name,
                        column_name=column.name,
                    )
                )
                continue

            if isinstance(node.expression, exp.Placeholder):
                unresolved.add(node.name)

        return (
            tuple(sorted(physical, key=_column_ref_sort_key)),
            tuple(sorted(unresolved)),
        )


def _column_ref_sort_key(
    ref: PhysicalColumnRef,
) -> tuple[str, str]:
    return (
        ref.table_full_name,
        ref.column_name,
    )
