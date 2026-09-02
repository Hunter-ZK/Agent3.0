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
    SchemaBinding,
    SchemaBindingKind,
    SchemaLinkingFailure,
    SchemaLinkingFailureCode,
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
        
        bindings: list[SchemaBinding] = []
        
        failures: list[
            SchemaLinkingFailure
        ] = []
        
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
                self._append_failure(
                    failures,
                    SchemaLinkingFailure(
                        code=(
                            SchemaLinkingFailureCode
                            .METADATA_ERROR
                        ),
                        term=table_name,
                        message=(
                            "Metadata lookup failed "
                            f"for table {table_name!r}: "
                            f"{result.error_message or ''}"
                        ),
                    ),
                )
                
                
            if (result.status is MetadataLookupStatus.NOT_FOUND or result.table is None):
                
                self._append_failure(
                    failures,
                    SchemaLinkingFailure(
                        code=(
                            SchemaLinkingFailureCode
                            .TABLE_NOT_FOUND
                        ),
                        term=table_name,
                        message=(
                            "Physical table "
                            f"{table_name!r} "
                            "was not found."
                        ),
                    ),
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
            
            bindings.append(
                SchemaBinding(
                    kind=(
                        SchemaBindingKind.TABLE
                    ),
                    logical_name=table_name,
                    physical_table=(
                        result.table.full_name
                    ),
                )
            )
            
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
                self._append_failure(
                    failures,
                    SchemaLinkingFailure(
                        code=(
                            SchemaLinkingFailureCode
                            .UNKNOWN_METRIC
                        ),
                        term=metric_name,
                        message=(
                            "Metric "
                            f"{metric_name!r} "
                            "was not found in the "
                            "current Semantic Model."
                        ),
                    ),
                )
                
                continue
            
            metric_outcome = (
                self._link_metric(
                    metric=metric,
                    linked_tables=(
                        linked_tables
                    ),
                )
            )

            if isinstance(
                metric_outcome,
                SchemaLinkingFailure,
            ):
                self._append_failure(
                    failures,
                    metric_outcome,
                )

                continue

            bindings.append(
                metric_outcome
            )

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
            
            column_outcome = (
                self._link_column(
                    column_name=column_name,
                    linked_tables=(
                        linked_tables
                    ),
                )
            )

            if isinstance(
                column_outcome,
                SchemaLinkingFailure,
            ):
                self._append_failure(
                    failures,
                    column_outcome,
                )

                continue

            resolved_units += 1

            bindings.append(
                column_outcome
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

            bindings=tuple(
                bindings
            ),
            
            failures=tuple(
                failures
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

    def _link_metric(
        self,
        *,
        metric: SemanticMetric,
        linked_tables: list[
            LinkedTable
        ],
    ) -> SchemaBinding | SchemaLinkingFailure:

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
            return SchemaLinkingFailure(
                code=(
                    SchemaLinkingFailureCode
                    .TABLE_NOT_FOUND
                ),
                term=metric.name,
                message=(
                    "Metric "
                    f"{metric.name!r} "
                    "cannot be linked because "
                    "its physical table "
                    f"{metric.table!r} "
                    "is unavailable."
                ),
            )

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
                return SchemaLinkingFailure(
                    code=(
                        SchemaLinkingFailureCode
                        .PHYSICAL_COLUMN_NOT_FOUND
                    ),
                    term=metric.name,
                    message=(
                        "Metric "
                        f"{metric.name!r} "
                        "requires physical column "
                        f"{column_name!r}, "
                        "but it was not found in "
                        f"{physical_table.full_name!r}."
                    ),
                )

        return SchemaBinding(
            kind=(
                SchemaBindingKind.METRIC
            ),
            logical_name=(
                metric.name
            ),
            physical_table=(
                physical_table.full_name
            ),
            physical_columns=(
                required_columns
            ),
        )

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
    def _link_column(
        *,
        column_name: str,
        linked_tables: list[
            LinkedTable
        ],
    ) -> SchemaBinding | None:
        
        normalized = column_name.strip().lower()

        matches: list[LinkedTable] = []
        
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
                matches.append(
                    linked_table
                )
                
        if not matches:
            return SchemaLinkingFailure(
                code=(
                    SchemaLinkingFailureCode
                    .PHYSICAL_COLUMN_NOT_FOUND
                ),
                term=column_name,
                message=(
                    "Physical column "
                    f"{column_name!r} "
                    "was not found in the "
                    "linked tables."
                ),
            )

        if len(matches) > 1:
            return SchemaLinkingFailure(
                code=(
                    SchemaLinkingFailureCode
                    .PHYSICAL_COLUMN_AMBIGUOUS
                ),
                term=column_name,
                message=(
                    "Physical column "
                    f"{column_name!r} "
                    "exists in multiple "
                    "linked tables."
                ),
            )
        
        physical_table = (matches[0].metadata)
        
        return SchemaBinding(
            kind=(SchemaBindingKind.COLUMN),
            logical_name=(column_name),
            physical_table=(physical_table.full_name),
            physical_columns=(normalized,),
        )

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
            

    @staticmethod
    def _append_failure(
        failures: list[
            SchemaLinkingFailure
        ],
        failure: SchemaLinkingFailure,
    ) -> None:
        """
        同一个 Linking unit 的同类型失败
        只记录一次。
        """

        key = (
            failure.code,
            failure.term.strip().lower(),
        )

        existing_keys = {
            (
                item.code,
                item.term
                .strip()
                .lower(),
            )
            for item
            in failures
        }

        if key not in existing_keys:
            failures.append(
                failure
            )