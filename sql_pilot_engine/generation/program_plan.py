from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgramCTEPlan:
    name: str
    purpose: str
    dependencies: tuple[str, ...] = ()
    source_tables: tuple[str, ...] = ()
    output_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        name = self.name.strip().lower()
        purpose = self.purpose.strip()
        if not name:
            raise ValueError("ProgramCTEPlan.name cannot be empty.")
        if not purpose:
            raise ValueError("ProgramCTEPlan.purpose cannot be empty.")

        dependencies = tuple(
            item.strip().lower()
            for item in self.dependencies
            if item.strip()
        )
        source_tables = tuple(
            item.strip().lower()
            for item in self.source_tables
            if item.strip()
        )
        output_columns = tuple(
            item.strip().lower()
            for item in self.output_columns
            if item.strip()
        )

        if name in dependencies:
            raise ValueError(
                f"CTE {name!r} cannot depend on itself."
            )
        if len(set(dependencies)) != len(dependencies):
            raise ValueError(
                f"CTE {name!r} dependencies must be unique."
            )
        if len(set(source_tables)) != len(source_tables):
            raise ValueError(
                f"CTE {name!r} source_tables must be unique."
            )

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "source_tables", source_tables)
        object.__setattr__(self, "output_columns", output_columns)


@dataclass(frozen=True, slots=True)
class ProgramStatementPlan:
    target_index: int
    purpose: str
    ctes: tuple[ProgramCTEPlan, ...]
    final_select_purpose: str
    final_dependencies: tuple[str, ...] = ()
    final_source_tables: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.target_index < 0:
            raise ValueError("target_index cannot be negative.")
        if not self.purpose.strip():
            raise ValueError("ProgramStatementPlan.purpose cannot be empty.")
        if not self.final_select_purpose.strip():
            raise ValueError(
                "ProgramStatementPlan.final_select_purpose cannot be empty."
            )

        names = tuple(item.name for item in self.ctes)
        if len(set(names)) != len(names):
            raise ValueError("CTE names must be unique within a statement.")

        known = set(names)
        for cte in self.ctes:
            unknown = set(cte.dependencies) - known
            if unknown:
                raise ValueError(
                    f"CTE {cte.name!r} references unknown dependencies: "
                    f"{sorted(unknown)!r}."
                )

        final_dependencies = tuple(
            item.strip().lower()
            for item in self.final_dependencies
            if item.strip()
        )
        unknown_final = set(final_dependencies) - known
        if unknown_final:
            raise ValueError(
                "Final SELECT references unknown CTE dependencies: "
                f"{sorted(unknown_final)!r}."
            )

        final_source_tables = tuple(
            item.strip().lower()
            for item in self.final_source_tables
            if item.strip()
        )
        if len(set(final_source_tables)) != len(final_source_tables):
            raise ValueError(
                "ProgramStatementPlan.final_source_tables must be unique."
            )

        object.__setattr__(self, "purpose", self.purpose.strip())
        object.__setattr__(
            self,
            "final_select_purpose",
            self.final_select_purpose.strip(),
        )
        object.__setattr__(self, "final_dependencies", final_dependencies)
        object.__setattr__(self, "final_source_tables", final_source_tables)

        # Validate DAG eagerly.
        self.topological_ctes()

    def topological_ctes(self) -> tuple[ProgramCTEPlan, ...]:
        by_name = {item.name: item for item in self.ctes}
        remaining = {
            name: set(item.dependencies)
            for name, item in by_name.items()
        }
        ordered: list[ProgramCTEPlan] = []
        resolved: set[str] = set()

        while remaining:
            ready = sorted(
                name
                for name, deps in remaining.items()
                if deps <= resolved
            )
            if not ready:
                cycle_nodes = sorted(remaining)
                raise ValueError(
                    "ProgramPlan contains a CTE dependency cycle involving: "
                    f"{cycle_nodes!r}."
                )

            for name in ready:
                ordered.append(by_name[name])
                resolved.add(name)
                remaining.pop(name)

        return tuple(ordered)


@dataclass(frozen=True, slots=True)
class ProgramPlan:
    statements: tuple[ProgramStatementPlan, ...]
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statements:
            raise ValueError("ProgramPlan requires at least one statement.")

        target_indexes = tuple(item.target_index for item in self.statements)
        if len(set(target_indexes)) != len(target_indexes):
            raise ValueError(
                "ProgramPlan target_index values must be unique."
            )

        assumptions = tuple(
            item.strip()
            for item in self.assumptions
            if item.strip()
        )
        object.__setattr__(self, "assumptions", assumptions)
