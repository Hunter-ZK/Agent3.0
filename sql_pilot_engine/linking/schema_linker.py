from __future__ import annotations

from collections.abc import Iterable

from sqlglot import (
    exp,
    parse_one,
)

from sqlglot.errors import (
    ParseError,
)

from sql_pilot_engine.context.semantic.models import (
    SemanticMetric,
    SemanticModel,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
    LinkedTable,
)

from sql_pilot_engine.metadata.models import (
    MetadataLookupStatus,
    TableMetadata,
)

from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)


class SchemaLinkingError(
    RuntimeError
):
    """
    Schema Linking Stage 自身无法继续执行。

    注意：

    这与 unresolved_terms 不同。

    unresolved_terms:
        当前业务对象没有找到可靠物理落点。

    SchemaLinkingError:
        Linking 基础设施或资产本身无法被正常处理，
        例如 MetadataProvider ERROR、
        Semantic Metric Expression 本身非法。
    """
    
class SchemaLinker:
    
    def __init__(
        self,
        *,
        metadata_provider: MetadataProvider,
        semantic_model: SemanticModel,
    ) -> None:
        
        self.metadata_provider = (
            metadata_provider
        )
        
        self.semantic_model = (
            semantic_model
        )
        
    def link(
        self,
        *,
        plan: QueryPlan,
    ) -> LinkedSchema:
        """
        将 QueryPlan 确定性映射到 Physical Schema。

        Phase 2.1 规则：

        1. 表级 Linking；
        2. Metric → SemanticMetric → Physical Table/Columns；
        3. Dimension / Group By 直接验证物理字段；
        4. 不进行字段级裁剪；
        5. 不使用 LLM 猜测；
        6. 不修改任何 Metadata / Semantic Asset。
        """
        
        if not plan.tables:
            raise SchemaLinkingError(
                "QueryPlan contains not tables."
            )
            
        linked_tables: list[LinkedTable] = []
        
        unresolved_terms: list[str] = []
        
        resolved_units = 0
        total_units = 0
        
        # ====================================================
        # 1. Physical Table Linking
        # ====================================================
        
        for table_name in (
            self._unique(
                plan.tables
            )
        ):
            total_units += 1
            
            result = (
                self.metadata_provider.get_table(
                    table_name
                )
            )
            
            if (result.status is MetadataLookupStatus.ERROR):
                raise SchemaLinkingError(
                    "Metadata lookup failed "
                    f"for table "
                    f"{table_name}: "
                    f"{result.error_message or ''}"
                )

            if (result.status is MetadataLookupStatus.NOT_FOUND or result.table is None):
                
                self._append_unique(
                    unresolved_terms,
                    table_name,
                )
                continue
            
            linked_tables.append(
                LinkedTable(
                    metadata=(
                        result.table
                    )
                )
            )
            
            resolved_units += 1
            
        # ====================================================
        # 2. Metric Linking
        # ====================================================
        
        for metric_name in (
            self._unique(
                plan.metrics
            )
        ):
            total_units += 1
            
            metric = (
                self.semantic_model
                .get_metric(
                    metric_name
                )
            )
            
            if metric is None:
                self._append_unique(
                    unresolved_terms,
                    metric_name,
                )
                
                continue
            
            if not self._metric_resolves(
                metric = metric,
                linked_tables=(
                    linked_tables
                ),
            ):
                self._append_unique(
                    unresolved_terms,
                    metric_name,
                )
                continue
            
            resolved_units += 1
            
        # ====================================================
        # 3. Dimension / Group By Linking
        # ====================================================
        
        physical_column_terms = (
            *plan.dimensions,
            *plan.group_by,
        )
        
        for column_name in (
            self._unique(
                physical_column_terms
            )
        ):
            
            total_units += 1
            
            if self._column_exists(
                column_name = column_name,
                linked_tables = (
                    linked_tables
                ),
            ):
                resolved_units += 1
                continue
            
            self._append_unique(
                unresolved_terms,
                column_name,
            )

        # ====================================================
        # 4. Linking Confidence
        # ====================================================
        
        if total_units == 0:
            linking_confidence = 0.0
        else:
            linking_confidence = (
                resolved_units
                / total_units
            )

        return LinkedSchema(
            tables=tuple(
                linked_tables
            ),

            unresolved_terms=tuple(
                unresolved_terms
            ),

            # F-25：
            # Phase 2.1 不进行字段级裁剪。
            omitted_column_count=0,

            linking_confidence=(
                linking_confidence
            ),
        )

    # ========================================================
    # Metric Resolution
    # ========================================================

    def _metric_resolves(
        self,
        *,
        metric: SemanticMetric,
        linked_tables: list[
            LinkedTable
        ],
    ) -> bool:

        linked_table = (
            self._find_linked_table(
                table_name=(
                    metric.table
                ),
                linked_tables=(
                    linked_tables
                ),
            )
        )

        if linked_table is None:
            return False

        required_columns = (
            self._extract_metric_columns(
                metric
            )
        )

        physical_table = (
            linked_table.metadata
        )

        for column_name in (
            required_columns
        ):

            if (
                physical_table
                .get_column(
                    column_name
                )
                is None
            ):
                return False

        return True

    @staticmethod
    def _extract_metric_columns(
        metric: SemanticMetric,
    ) -> tuple[str, ...]:

        try:
            tree = parse_one(
                metric.expression
            )

        except ParseError as exc:
            raise SchemaLinkingError(
                "Semantic metric "
                f"{metric.name!r} "
                "contains an invalid SQL "
                "expression."
            ) from exc

        columns = []

        for column in tree.find_all(
            exp.Column
        ):
            normalized = (
                column.name
                .strip()
                .lower()
            )

            if (
                normalized
                and normalized
                not in columns
            ):
                columns.append(
                    normalized
                )

        return tuple(columns)

    # ========================================================
    # Physical Column Resolution
    # ========================================================

    @staticmethod
    def _column_exists(
        *,
        column_name: str,
        linked_tables: list[
            LinkedTable
        ],
    ) -> bool:

        for linked_table in (
            linked_tables
        ):

            if (
                linked_table
                .metadata
                .get_column(
                    column_name
                )
                is not None
            ):
                return True

        return False

    # ========================================================
    # Table Resolution
    # ========================================================

    @staticmethod
    def _find_linked_table(
        *,
        table_name: str,
        linked_tables: list[
            LinkedTable
        ],
    ) -> LinkedTable | None:

        normalized = (
            table_name
            .strip()
            .lower()
        )

        bare_name = (
            normalized
            .split(".")[-1]
        )

        for linked_table in (
            linked_tables
        ):

            physical_name = (
                linked_table
                .metadata
                .full_name
                .lower()
            )

            if (
                physical_name
                == normalized
            ):
                return linked_table

            if (
                physical_name
                .split(".")[-1]
                == bare_name
            ):
                return linked_table

        return None

    # ========================================================
    # Utilities
    # ========================================================

    @staticmethod
    def _unique(
        values: Iterable[str],
    ) -> tuple[str, ...]:

        result: list[str] = []

        for value in values:

            normalized = (
                value.strip()
            )

            if (
                normalized
                and normalized
                not in result
            ):
                result.append(
                    normalized
                )

        return tuple(result)

    @staticmethod
    def _append_unique(
        values: list[str],
        value: str,
    ) -> None:

        normalized = (
            value.strip()
        )

        if (
            normalized
            and normalized
            not in values
        ):
            values.append(
                normalized
            )