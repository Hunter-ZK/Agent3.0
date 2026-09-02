from __future__ import annotations

from sqlglot import (
    exp,
    parse,
)

from sqlglot.errors import (
    ParseError,
)

from sql_pilot_engine.context.semantic.models import (
    SemanticFilter,
    SemanticMetric,
    SemanticModel,
)

from sql_pilot_engine.generation.models import (
    CompilationEvidence,
    CompilationFallbackReason,
    GeneratedSQL,
    MetricCompilationOutcome,
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
    SchemaBindingKind,
)

from sql_pilot_engine.metadata.models import (
    TableMetadata,
)


class MetricSQLCompiler:
    """
    Simple Metric → SQL Deterministic Compiler。

    第一版只负责：

        single table
        +
        simple metrics
        +
        dimensions
        +
        group by
        +
        simple filters

    Compiler 不负责：

    - Planning
    - Schema Linking
    - Semantic Asset 治理
    - Trusted SQL
    - Semantic Validation
    - LLM fallback routing

    不支持的输入返回 NOT_COMPILABLE，
    而不是抛业务异常。
    """

    _SUPPORTED_AGGREGATIONS = {
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "count_distinct",
    }

    def __init__(
        self,
        *,
        semantic_model: SemanticModel,
    ) -> None:

        self._semantic_model = (
            semantic_model
        )

    # ========================================================
    # Public API
    # ========================================================

    def compile(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        dialect: str,
    ) -> MetricCompilationOutcome:

        if not linked_schema.resolved:
            return self._fallback(
                CompilationFallbackReason
                .UNRESOLVED_SCHEMA,

                "LinkedSchema is unresolved.",
            )

        if not plan.metrics:
            return self._fallback(
                CompilationFallbackReason
                .NO_METRIC,

                "QueryPlan contains no metric.",
            )

        if (
            len(plan.tables) != 1
            or len(
                linked_schema.tables
            )
            != 1
        ):
            return self._fallback(
                CompilationFallbackReason
                .MULTI_TABLE,

                (
                    "Metric Compiler V1 "
                    "supports one physical "
                    "table only."
                ),
            )

        table = (
            linked_schema
            .tables[0]
            .metadata
        )

        grouping_check = (
            self._validate_grouping(
                plan
            )
        )

        if not grouping_check:
            return self._fallback(
                CompilationFallbackReason
                .INVALID_GROUPING,

                (
                    "Metric query dimensions "
                    "must match group_by "
                    "for deterministic "
                    "compilation."
                ),
            )

        dimension_columns = (
            self
            ._resolve_dimension_columns(
                plan=plan,
                linked_schema=(
                    linked_schema
                ),
                table=table,
            )
        )

        if dimension_columns is None:
            return self._fallback(
                CompilationFallbackReason
                .UNRESOLVED_SCHEMA,

                (
                    "Dimension or group_by "
                    "binding is unavailable."
                ),
            )

        (
            metric_selects,
            metric_expressions,
            metrics,
            metric_error,
        ) = self._compile_metrics(
            plan=plan,

            linked_schema=(
                linked_schema
            ),

            table=table,

            dialect=dialect,
        )

        if metric_error is not None:
            return metric_error

        predicates: list[
            exp.Expression
        ] = []

        # ====================================================
        # Metric Fixed Filters
        # ====================================================

        for metric in metrics:

            for fixed_filter in (
                metric.fixed_filters
            ):

                predicate = (
                    self
                    ._build_semantic_filter(
                        semantic_filter=(
                            fixed_filter
                        ),

                        table=table,
                    )
                )

                if predicate is None:
                    return self._fallback(
                        CompilationFallbackReason
                        .UNSUPPORTED_FILTER,

                        (
                            "Metric fixed filter "
                            "cannot be compiled: "
                            f"{fixed_filter.column} "
                            f"{fixed_filter.operator}"
                        ),
                    )

                predicates.append(
                    predicate
                )

        # ====================================================
        # Planner Filters
        # ====================================================

        for filter_text in (
            plan.filters
        ):

            predicate = (
                self
                ._parse_plan_filter(
                    filter_text=filter_text,

                    dialect=dialect,

                    table=table,
                )
            )

            if predicate is None:
                return self._fallback(
                    CompilationFallbackReason
                    .UNSUPPORTED_FILTER,

                    (
                        "Planner filter is "
                        "outside the compiler "
                        "safe subset: "
                        f"{filter_text}"
                    ),
                )

            predicates.append(
                predicate
            )

        predicates = (
            self._dedupe_predicates(
                predicates=predicates,
                dialect=dialect,
            )
        )

        select_expressions: list[
            exp.Expression
        ] = []

        for column_name in (
            dimension_columns
        ):
            select_expressions.append(
                exp.column(
                    column_name
                )
            )

        select_expressions.extend(
            metric_selects
        )

        query = (
            exp.select(
                *select_expressions
            )
            .from_(
                exp.to_table(
                    table.full_name
                )
            )
        )

        if predicates:

            condition = (
                predicates[0]
            )

            for predicate in (
                predicates[1:]
            ):
                condition = exp.and_(
                    condition,
                    predicate,
                )

            query = query.where(
                condition
            )

        group_by_columns = (
            self
            ._resolve_group_by_columns(
                plan=plan,

                linked_schema=(
                    linked_schema
                ),

                table=table,
            )
        )

        if group_by_columns is None:
            return self._fallback(
                CompilationFallbackReason
                .UNRESOLVED_SCHEMA,

                (
                    "Group-by physical "
                    "binding is unavailable."
                ),
            )

        if group_by_columns:

            query = query.group_by(
                *(
                    exp.column(
                        column_name
                    )
                    for column_name
                    in group_by_columns
                )
            )

        sql = query.sql(
            dialect=dialect
        )

        filter_expressions = tuple(
            predicate.sql(
                dialect=dialect
            )
            for predicate
            in predicates
        )

        evidence = (
            CompilationEvidence(
                metric_names=tuple(
                    metric.name
                    for metric
                    in metrics
                ),

                physical_table=(
                    table.full_name
                ),

                metric_expressions=(
                    metric_expressions
                ),

                dimension_columns=(
                    dimension_columns
                ),

                filter_expressions=(
                    filter_expressions
                ),

                group_by_columns=(
                    group_by_columns
                ),
            )
        )

        return (
            MetricCompilationOutcome
            .compiled(
                generated_sql=(
                    GeneratedSQL(
                        sql=sql,
                        dialect=dialect,
                    )
                ),

                evidence=evidence,
            )
        )

    # ========================================================
    # Metrics
    # ========================================================

    def _compile_metrics(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        table: TableMetadata,
        dialect: str,
    ) -> tuple[
        list[exp.Expression],
        tuple[str, ...],
        tuple[SemanticMetric, ...],
        MetricCompilationOutcome | None,
    ]:

        selects: list[
            exp.Expression
        ] = []

        rendered: list[str] = []

        metrics: list[
            SemanticMetric
        ] = []

        for metric_name in (
            plan.metrics
        ):

            metric = (
                self
                ._semantic_model
                .get_metric(
                    metric_name
                )
            )

            if metric is None:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason
                        .UNRESOLVED_SCHEMA,

                        (
                            "Metric is unavailable "
                            "in SemanticModel: "
                            f"{metric_name}"
                        ),
                    ),
                )

            if (
                metric.aggregation
                is None
                or metric.source_column
                is None
            ):
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason
                        .COMPLEX_EXPRESSION,

                        (
                            "Metric requires "
                            "expression-level "
                            "generation: "
                            f"{metric.name}"
                        ),
                    ),
                )

            aggregation = (
                metric.aggregation
                .strip()
                .lower()
            )

            if (
                aggregation
                not in (
                    self
                    ._SUPPORTED_AGGREGATIONS
                )
            ):
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason
                        .UNSUPPORTED_AGGREGATION,

                        (
                            "Unsupported metric "
                            "aggregation: "
                            f"{aggregation}"
                        ),
                    ),
                )

            binding = (
                linked_schema
                .get_binding(
                    kind=(
                        SchemaBindingKind
                        .METRIC
                    ),

                    logical_name=(
                        metric.name
                    ),
                )
            )

            if binding is None:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason
                        .UNRESOLVED_SCHEMA,

                        (
                            "Metric has no "
                            "SchemaBinding: "
                            f"{metric.name}"
                        ),
                    ),
                )

            if not self._table_matches(
                binding.physical_table,
                table.full_name,
            ):
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason
                        .MULTI_TABLE,

                        (
                            "Metrics resolve to "
                            "different physical "
                            "tables."
                        ),
                    ),
                )

            source_column = (
                metric.source_column
                .strip()
            )

            if (
                table.get_column(
                    source_column
                )
                is None
            ):
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason
                        .UNRESOLVED_SCHEMA,

                        (
                            "Metric source column "
                            "is unavailable in "
                            "LinkedSchema."
                        ),
                    ),
                )

            binding_columns = {
                column
                .strip()
                .lower()

                for column
                in binding.physical_columns
            }

            if (
                source_column.lower()
                not in binding_columns
            ):
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason
                        .UNRESOLVED_SCHEMA,

                        (
                            "Metric source column "
                            "was not confirmed by "
                            "SchemaBinding."
                        ),
                    ),
                )

            aggregate_expression = (
                self._build_aggregate(
                    aggregation=aggregation,

                    source_column=(
                        source_column
                    ),
                )
            )

            aliased_expression = (
                exp.alias_(
                    aggregate_expression,
                    metric.name,
                    quoted=False,
                )
            )

            selects.append(
                aliased_expression
            )

            rendered.append(
                aggregate_expression
                .sql(
                    dialect=dialect
                )
            )

            metrics.append(
                metric
            )

        return (
            selects,
            tuple(rendered),
            tuple(metrics),
            None,
        )

    @staticmethod
    def _build_aggregate(
        *,
        aggregation: str,
        source_column: str,
    ) -> exp.Expression:

        column = exp.column(
            source_column
        )

        if aggregation == "sum":
            return exp.Sum(
                this=column
            )

        if aggregation == "avg":
            return exp.Avg(
                this=column
            )

        if aggregation == "min":
            return exp.Min(
                this=column
            )

        if aggregation == "max":
            return exp.Max(
                this=column
            )

        if aggregation == "count":
            return exp.Count(
                this=column
            )

        if (
            aggregation
            == "count_distinct"
        ):
            return exp.Count(
                this=exp.Distinct(
                    expressions=[
                        column
                    ]
                )
            )

        raise ValueError(
            "Unsupported aggregation "
            f"{aggregation!r}."
        )

    # ========================================================
    # Dimensions / Grouping
    # ========================================================

    @staticmethod
    def _validate_grouping(
        plan: QueryPlan,
    ) -> bool:

        dimensions = {
            value.strip().lower()
            for value
            in plan.dimensions
        }

        group_by = {
            value.strip().lower()
            for value
            in plan.group_by
        }

        return (
            dimensions
            == group_by
        )

    def _resolve_dimension_columns(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        table: TableMetadata,
    ) -> tuple[str, ...] | None:

        return (
            self._resolve_columns(
                logical_names=(
                    plan.dimensions
                ),

                linked_schema=(
                    linked_schema
                ),

                table=table,
            )
        )

    def _resolve_group_by_columns(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        table: TableMetadata,
    ) -> tuple[str, ...] | None:

        return (
            self._resolve_columns(
                logical_names=(
                    plan.group_by
                ),

                linked_schema=(
                    linked_schema
                ),

                table=table,
            )
        )

    @staticmethod
    def _resolve_columns(
        *,
        logical_names: tuple[
            str,
            ...
        ],
        linked_schema: LinkedSchema,
        table: TableMetadata,
    ) -> tuple[str, ...] | None:

        result: list[str] = []

        for logical_name in (
            logical_names
        ):

            binding = (
                linked_schema
                .get_binding(
                    kind=(
                        SchemaBindingKind
                        .COLUMN
                    ),

                    logical_name=(
                        logical_name
                    ),
                )
            )

            if binding is None:
                return None

            if (
                len(
                    binding
                    .physical_columns
                )
                != 1
            ):
                return None

            if not (
                MetricSQLCompiler
                ._table_matches(
                    binding.physical_table,
                    table.full_name,
                )
            ):
                return None

            physical_column = (
                binding
                .physical_columns[0]
            )

            if (
                table.get_column(
                    physical_column
                )
                is None
            ):
                return None

            result.append(
                physical_column
            )

        return tuple(result)

    # ========================================================
    # Planner Filter
    # ========================================================

    def _parse_plan_filter(
        self,
        *,
        filter_text: str,
        dialect: str,
        table: TableMetadata,
    ) -> exp.Expression | None:

        normalized = (
            filter_text.strip()
        )

        if not normalized:
            return None

        # 不能直接把 Planner 字符串
        # 拼进最终 SQL。
        #
        # 包进 SELECT WHERE 后完整解析，
        # 同时要求最终只能得到一个 Statement。
        try:
            statements = parse(
                (
                    "SELECT 1 WHERE "
                    f"{normalized}"
                ),

                read=dialect,
            )

        except ParseError:
            return None

        if (
            len(statements)
            != 1
        ):
            return None

        statement = (
            statements[0]
        )

        if not isinstance(
            statement,
            exp.Select,
        ):
            return None

        where = (
            statement.args.get(
                "where"
            )
        )

        if not isinstance(
            where,
            exp.Where,
        ):
            return None

        predicate = (
            where.this
        )

        if not self._validate_predicate(
            predicate=predicate,
            table=table,
        ):
            return None

        return predicate.copy()

    def _validate_predicate(
        self,
        *,
        predicate: exp.Expression,
        table: TableMetadata,
    ) -> bool:

        if isinstance(
            predicate,
            exp.Paren,
        ):
            return (
                self
                ._validate_predicate(
                    predicate=(
                        predicate.this
                    ),

                    table=table,
                )
            )

        if isinstance(
            predicate,
            exp.And,
        ):
            return (
                self._validate_predicate(
                    predicate=(
                        predicate.this
                    ),
                    table=table,
                )
                and
                self._validate_predicate(
                    predicate=(
                        predicate.expression
                    ),
                    table=table,
                )
            )

        if isinstance(
            predicate,
            (
                exp.EQ,
                exp.NEQ,
                exp.GT,
                exp.GTE,
                exp.LT,
                exp.LTE,
            ),
        ):
            return (
                self._valid_column(
                    predicate.this,
                    table,
                )
                and
                self._is_literal(
                    predicate.expression
                )
            )

        if isinstance(
            predicate,
            exp.In,
        ):
            if not self._valid_column(
                predicate.this,
                table,
            ):
                return False

            if (
                predicate.args.get(
                    "query"
                )
                is not None
            ):
                return False

            values = tuple(
                predicate.expressions
            )

            return (
                bool(values)
                and all(
                    self._is_literal(
                        value
                    )
                    for value
                    in values
                )
            )

        if isinstance(
            predicate,
            exp.Between,
        ):
            return (
                self._valid_column(
                    predicate.this,
                    table,
                )
                and
                self._is_literal(
                    predicate.args.get(
                        "low"
                    )
                )
                and
                self._is_literal(
                    predicate.args.get(
                        "high"
                    )
                )
            )

        return False

    @staticmethod
    def _is_literal(
        value,
    ) -> bool:

        return isinstance(
            value,
            (
                exp.Literal,
                exp.Boolean,
            ),
        )

    @staticmethod
    def _valid_column(
        expression,
        table: TableMetadata,
    ) -> bool:

        if not isinstance(
            expression,
            exp.Column,
        ):
            return False

        if (
            table.get_column(
                expression.name
            )
            is None
        ):
            return False

        qualifier = (
            expression.table
        )

        if not qualifier:
            return True

        normalized = (
            qualifier
            .strip()
            .lower()
        )

        full_name = (
            table.full_name
            .strip()
            .lower()
        )

        bare_name = (
            full_name
            .split(".")[-1]
        )

        return normalized in {
            full_name,
            bare_name,
        }

    # ========================================================
    # Approved Fixed Filter
    # ========================================================

    def _build_semantic_filter(
        self,
        *,
        semantic_filter: SemanticFilter,
        table: TableMetadata,
    ) -> exp.Expression | None:

        column_name = (
            semantic_filter.column
            .strip()
        )

        if (
            table.get_column(
                column_name
            )
            is None
        ):
            return None

        operator = (
            semantic_filter.operator
            .strip()
            .lower()
        )

        operator = {
            "=": "eq",
            "==": "eq",
            "eq": "eq",

            "!=": "neq",
            "<>": "neq",
            "neq": "neq",

            ">": "gt",
            "gt": "gt",

            ">=": "gte",
            "gte": "gte",

            "<": "lt",
            "lt": "lt",

            "<=": "lte",
            "lte": "lte",

            "in": "in",

            "between": "between",
        }.get(
            operator
        )

        if operator is None:
            return None

        column = exp.column(
            column_name
        )

        value = (
            semantic_filter.value
        )

        if operator == "in":

            values = (
                value
                if isinstance(
                    value,
                    tuple,
                )
                else (
                    value,
                )
            )

            expressions = []

            for item in values:

                literal = (
                    self._literal(
                        item
                    )
                )

                if literal is None:
                    return None

                expressions.append(
                    literal
                )

            if not expressions:
                return None

            return exp.In(
                this=column,

                expressions=(
                    expressions
                ),
            )

        if operator == "between":

            if (
                not isinstance(
                    value,
                    tuple,
                )
                or len(value) != 2
            ):
                return None

            low = self._literal(
                value[0]
            )

            high = self._literal(
                value[1]
            )

            if (
                low is None
                or high is None
            ):
                return None

            return exp.Between(
                this=column,
                low=low,
                high=high,
            )

        literal = (
            self._literal(
                value
            )
        )

        if literal is None:
            return None

        builders = {
            "eq": exp.EQ,
            "neq": exp.NEQ,
            "gt": exp.GT,
            "gte": exp.GTE,
            "lt": exp.LT,
            "lte": exp.LTE,
        }

        builder = (
            builders.get(
                operator
            )
        )

        if builder is None:
            return None

        return builder(
            this=column,
            expression=literal,
        )

    @staticmethod
    def _literal(
        value,
    ) -> exp.Expression | None:

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return exp.Boolean(
                this=value
            )

        if isinstance(
            value,
            (int, float),
        ):
            return (
                exp.Literal.number(
                    str(value)
                )
            )

        if isinstance(
            value,
            str,
        ):
            return (
                exp.Literal.string(
                    value
                )
            )

        return None

    # ========================================================
    # Utilities
    # ========================================================

    @staticmethod
    def _dedupe_predicates(
        *,
        predicates: list[
            exp.Expression
        ],
        dialect: str,
    ) -> list[
        exp.Expression
    ]:

        result: list[
            exp.Expression
        ] = []

        seen: set[str] = set()

        for predicate in (
            predicates
        ):

            key = (
                predicate
                .sql(
                    dialect=dialect
                )
                .lower()
                .replace(
                    " ",
                    "",
                )
            )

            if key in seen:
                continue

            seen.add(key)

            result.append(
                predicate
            )

        return result

    @staticmethod
    def _table_matches(
        left: str,
        right: str,
    ) -> bool:

        normalized_left = (
            left.strip().lower()
        )

        normalized_right = (
            right.strip().lower()
        )

        if (
            normalized_left
            == normalized_right
        ):
            return True

        return (
            normalized_left
            .split(".")[-1]
            ==
            normalized_right
            .split(".")[-1]
        )

    @staticmethod
    def _fallback(
        reason: CompilationFallbackReason,
        detail: str,
    ) -> MetricCompilationOutcome:

        return (
            MetricCompilationOutcome
            .fallback(
                fallback_reason=reason,
                reason=detail,
            )
        )