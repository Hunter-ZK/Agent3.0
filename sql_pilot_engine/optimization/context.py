from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
)
from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)
from sql_pilot_engine.schemas.requests import (
    SQLOptimizeRequest,
)
from sql_pilot_engine.schemas.responses import (
    SQLExplainResponse,
)


@dataclass(
    frozen=True,
    slots=True,
)
class SQLOptimizationContext:
    """
    一次 SQL Optimization 的 Request-scoped Context。

    V0.2 当前包含：
    - Trusted SQL
    - Optimization Goals
    - Explain 结果
    - Physical Metadata

    后续再增加：
    - RAG Best Practices
    - Verified SQL
    - EXPLAIN Plan
    - Execution Stats
    """

    sql: str
    dialect: str

    optimization_goals: tuple[
        str,
        ...,
    ] = ()

    explain_context: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    metadata_context: tuple[
        dict[str, Any],
        ...,
    ] = ()


class SQLOptimizationContextBuilder:

    def build(
        self,
        *,
        request: SQLOptimizeRequest,
        explain_response: (
            SQLExplainResponse | None
        ),
        metadata_provider: (
            MetadataProvider | None
        ),
    ) -> SQLOptimizationContext:

        explain_context = (
            self._build_explain_context(
                explain_response
            )
        )

        metadata_context = (
            self._build_metadata_context(
                explain_response=(
                    explain_response
                ),
                metadata_provider=(
                    metadata_provider
                ),
            )
        )

        return SQLOptimizationContext(
            sql=request.sql,
            dialect=request.dialect,
            optimization_goals=tuple(
                request.optimization_goals
            ),
            explain_context=(
                explain_context
            ),
            metadata_context=(
                metadata_context
            ),
        )

    @staticmethod
    def _build_explain_context(
        explain_response: (
            SQLExplainResponse | None
        ),
    ) -> dict[str, Any]:

        if (
            explain_response is None
            or not explain_response.success
        ):
            return {}

        return {
            "sql_summary": (
                explain_response.sql_summary
            ),
            "business_purpose": (
                explain_response
                .business_purpose
            ),
            "main_tables": (
                explain_response.main_tables
            ),
            "output_columns": (
                explain_response
                .output_columns
            ),
            "cte_steps": (
                explain_response.cte_steps
            ),
            "cte_dependencies": (
                explain_response
                .cte_dependencies
            ),
            "suspicious_points": (
                explain_response
                .suspicious_points
            ),
            "uncertainties": (
                explain_response
                .uncertainties
            ),
        }

    def _build_metadata_context(
        self,
        *,
        explain_response: (
            SQLExplainResponse | None
        ),
        metadata_provider: (
            MetadataProvider | None
        ),
    ) -> tuple[
        dict[str, Any],
        ...,
    ]:

        if metadata_provider is None:
            return ()

        if (
            explain_response is None
            or not explain_response.success
        ):
            return ()

        table_names = (
            self._extract_table_names(
                explain_response
            )
        )

        metadata_items: list[
            dict[str, Any]
        ] = []

        for table_name in table_names:

            result = (
                metadata_provider
                .get_table(
                    table_name
                )
            )

            if (
                result.status
                != MetadataLookupStatus.FOUND
                or result.table is None
            ):
                continue

            table = result.table

            metadata_items.append(
                {
                    "table_name": (
                        table.full_name
                    ),
                    "description": (
                        table.description
                    ),
                    "layer": (
                        table.layer
                    ),
                    "partition_fields": list(
                        table.partition_fields
                    ),
                    "row_count": (
                        table.row_count
                    ),
                    "size_bytes": (
                        table.size_bytes
                    ),
                    "columns": [
                        {
                            "name": column.name,
                            "data_type": (
                                column.data_type
                            ),
                            "nullable": (
                                column.nullable
                            ),
                            "description": (
                                column.description
                            ),
                            "distinct_count": (
                                column
                                .distinct_count
                            ),
                        }
                        for column
                        in table.columns.values()
                    ],
                }
            )

        return tuple(
            metadata_items
        )

    @staticmethod
    def _extract_table_names(
        explain_response: SQLExplainResponse,
    ) -> tuple[str, ...]:

        names: list[str] = []

        for item in (
            explain_response.main_tables
        ):
            table_name = (
                item.get("table_name")
                if isinstance(item, dict)
                else None
            )

            if not table_name:
                continue

            if table_name not in names:
                names.append(
                    table_name
                )

        return tuple(
            names
        )