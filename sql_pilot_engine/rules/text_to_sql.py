from __future__ import annotations

from sql_pilot_engine.analysis.facts import (
    PredicateFact,
    SQLFacts,
)

from sql_pilot_engine.context.semantic.models import (
    SemanticFilter,
    SemanticMetric,
)

from sql_pilot_engine.core.context import (
    ReviewContext,
)

from sql_pilot_engine.core.enums import (
    IssueAction,
    Severity,
)

from sql_pilot_engine.core.models import (
    Issue,
)

from sql_pilot_engine.rules.base import (
    Rule,
)

from sql_pilot_engine.rules.helpers import (
    make_issue,
)


# ============================================================
# Rollout Policy
# ============================================================
#
# 技术方案要求：
#
# 新 Evidence Rule
# 先 ADVISORY
# ↓
# Evaluation 确认无系统性误报
# ↓
# 再升级 BLOCK
#
# 这里把 rollout action 集中定义，
# 后续升级不再修改规则算法本身。
# ============================================================

METRIC_TABLE_ACTION = (
    IssueAction.ADVISORY
)

METRIC_AGGREGATION_ACTION = (
    IssueAction.ADVISORY
)

METRIC_FIXED_FILTER_ACTION = (
    IssueAction.ADVISORY
)

PARTITION_CONSTRAINT_ACTION = (
    IssueAction.ADVISORY
)


# ============================================================
# Shared Helpers
# ============================================================

def _normalize_name(
    value: str,
) -> str:
    return (
        value
        .strip()
        .lower()
    )


def _bare_table_name(
    value: str,
) -> str:
    return (
        _normalize_name(value)
        .split(".")[-1]
    )


def _table_matches(
    actual: str,
    expected: str,
) -> bool:
    """
    支持：

        ods_xxx

    与：

        project.ods_xxx

    的确定性表名匹配。

    不做模糊匹配。
    """

    normalized_actual = (
        _normalize_name(actual)
    )

    normalized_expected = (
        _normalize_name(expected)
    )

    if (
        normalized_actual
        == normalized_expected
    ):
        return True

    return (
        _bare_table_name(
            normalized_actual
        )
        == _bare_table_name(
            normalized_expected
        )
    )


def _selected_metrics(
    context: ReviewContext,
) -> tuple[
    SemanticMetric,
    ...
]:
    """
    从当前 QueryPlan 中取得本任务真正要求的 Metric。

    QueryPlan：
        本次用户要什么。

    SemanticModel：
        这个 Metric 的权威结构化定义是什么。

    如果 Trust Evidence 不存在，
    本规则直接 not_applicable。

    Metadata / Evidence absence
    不能被解释成 false。
    """

    evidence = (
        context.trust_evidence
    )

    if evidence is None:
        return ()

    result: list[
        SemanticMetric
    ] = []

    seen: set[str] = set()

    for metric_name in (
        evidence
        .query_plan
        .metrics
    ):
        metric = (
            evidence
            .semantic_model
            .get_metric(
                metric_name
            )
        )

        # UNKNOWN_METRIC 已属于
        # Planning / Linking Failure 范畴。
        #
        # Trust Rule 不重新制造
        # 第二套失败判断。
        if metric is None:
            continue

        normalized = (
            _normalize_name(
                metric.name
            )
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        result.append(
            metric
        )

    return tuple(
        result
    )


def _format_source_tables(
    facts: SQLFacts,
) -> str:
    return (
        ", ".join(
            facts.source_tables
        )
        or "<none>"
    )


def _format_aggregate_facts(
    facts: SQLFacts,
) -> str:

    values: list[str] = []

    for aggregate in (
        facts.aggregate_facts
    ):
        column_name = (
            aggregate.column.name
            if aggregate.column
            is not None
            else "<complex_expression>"
        )

        values.append(
            (
                f"{aggregate.function}"
                f"({column_name})"
            )
        )

    return (
        ", ".join(values)
        or "<none>"
    )


def _normalize_filter_operator(
    operator: str,
) -> str | None:

    normalized = (
        operator
        .strip()
        .lower()
    )

    mapping = {
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
    }

    return mapping.get(
        normalized
    )


def _value_key(
    value,
) -> tuple[
    str,
    object,
]:
    """
    保留 Literal 类型。

    Python 中：
        True == 1

    但 SQL / Semantic Evidence 中
    不应因此把 BOOL 和 INT
    自动视为同一业务值。
    """

    return (
        type(value).__name__,
        value,
    )


def _values_match(
    actual: tuple,
    expected: tuple,
    *,
    unordered: bool,
) -> bool:

    actual_keys = tuple(
        _value_key(value)
        for value
        in actual
    )

    expected_keys = tuple(
        _value_key(value)
        for value
        in expected
    )

    if unordered:
        return (
            len(actual_keys)
            == len(expected_keys)
            and set(actual_keys)
            == set(expected_keys)
        )

    return (
        actual_keys
        == expected_keys
    )


def _semantic_filter_values(
    semantic_filter: SemanticFilter,
) -> tuple:

    value = (
        semantic_filter.value
    )

    if isinstance(
        value,
        tuple,
    ):
        return value

    return (
        value,
    )


def _predicate_matches_filter(
    predicate: PredicateFact,
    semantic_filter: SemanticFilter,
) -> bool:

    if (
        _normalize_name(
            predicate.column.name
        )
        != _normalize_name(
            semantic_filter.column
        )
    ):
        return False

    expected_operator = (
        _normalize_filter_operator(
            semantic_filter.operator
        )
    )

    # 当前 SQLFacts 无法形式化证明的
    # Operator 不做确定性判断。
    if expected_operator is None:
        return False

    if (
        predicate.operator
        != expected_operator
    ):
        return False

    expected_values = (
        _semantic_filter_values(
            semantic_filter
        )
    )

    return _values_match(
        predicate.values,
        expected_values,
        unordered=(
            expected_operator
            == "in"
        ),
    )


def _table_qualifiers(
    *,
    facts: SQLFacts,
    physical_table: str,
) -> set[str]:
    """
    返回 SQL 中能够确定指向
    某张物理表的 qualifier / alias。
    """

    qualifiers = {
        _normalize_name(
            physical_table
        ),
        _bare_table_name(
            physical_table
        ),
    }

    for reference in (
        facts.table_references
    ):
        if not _table_matches(
            reference.physical_name,
            physical_table,
        ):
            continue

        qualifiers.add(
            _normalize_name(
                reference.physical_name
            )
        )

        qualifiers.add(
            _bare_table_name(
                reference.physical_name
            )
        )

        if reference.alias:
            qualifiers.add(
                _normalize_name(
                    reference.alias
                )
            )

    return qualifiers


def _partition_constraint_status(
    *,
    facts: SQLFacts,
    physical_table: str,
    partition_fields: tuple[
        str,
        ...
    ],
) -> bool | None:
    """
    返回：

        True
            已找到能够确定属于该表的
            Partition Predicate。

        False
            当前可抽取 Evidence 中
            没找到 Partition Predicate。

        None
            当前 SQL 结构存在歧义，
            不能安全判断。

    注意：

    SQLFacts.has_partition_clause
    描述的是 INSERT PARTITION，
    不能用于 SELECT WHERE 分区约束。
    """

    normalized_fields = {
        _normalize_name(
            field
        )
        for field
        in partition_fields
        if field.strip()
    }

    if not normalized_fields:
        return None

    source_tables = tuple(
        facts.source_tables
    )

    if not any(
        _table_matches(
            source_table,
            physical_table,
        )
        for source_table
        in source_tables
    ):
        return None

    qualifiers = (
        _table_qualifiers(
            facts=facts,
            physical_table=(
                physical_table
            ),
        )
    )

    multiple_source_tables = (
        len(source_tables) > 1
    )

    ambiguous_unqualified = False

    for predicate in (
        facts.predicate_facts
    ):

        if (
            _normalize_name(
                predicate.column.name
            )
            not in normalized_fields
        ):
            continue

        qualifier = (
            predicate.column.qualifier
        )

        if qualifier:

            if (
                _normalize_name(
                    qualifier
                )
                in qualifiers
            ):
                return True

            continue

        # 单表 SQL：
        # 无 qualifier 的 partition column
        # 可以确定属于该表。
        if not multiple_source_tables:
            return True

        # 多表 SQL：
        # dt = ...
        # 无法证明属于哪张表。
        #
        # 不能因为证据不足就判断缺失。
        ambiguous_unqualified = True

    if ambiguous_unqualified:
        return None

    return False


# ============================================================
# Rule 1
# Text-to-SQL Read Only
# ============================================================

def check_text_to_sql_read_only(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:

    _ = sql

    facts = context.sql_facts

    if facts is None:
        return []

    if not facts.has_write_operation:
        return []

    return [
        make_issue(
            rule_id=(
                "TEXT_TO_SQL_READ_ONLY"
            ),

            title=(
                "Text-to-SQL "
                "不允许写操作"
            ),

            severity=Severity.HIGH,

            message=(
                "当前 Text-to-SQL "
                "能力生成了写入或结构变更 SQL。"
            ),

            suggestion=(
                "Text-to-SQL V1 "
                "只能生成只读查询 SQL。"
            ),

            evidence=(
                "statement_types="
                f"{facts.statement_types}"
            ),

            category="safety",

            action=(
                IssueAction.BLOCK
            ),

            auto_fixable=False,
        )
    ]


# ============================================================
# Rule 2
# Metric → Source Table
# ============================================================

def check_metric_table(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:
    """
    Evidence：

    QueryPlan
        ↓
    当前任务选择哪些 Metric

    SemanticMetric.table
        ↓
    Metric 的 Approved Source Table

    SQLFacts.source_tables
        ↓
    SQL 实际读取哪些表
    """

    _ = sql

    facts = context.sql_facts

    if (
        facts is None
        or context.trust_evidence
        is None
    ):
        return []

    issues: list[Issue] = []

    for metric in (
        _selected_metrics(
            context
        )
    ):

        if any(
            _table_matches(
                source_table,
                metric.table,
            )
            for source_table
            in facts.source_tables
        ):
            continue

        issues.append(
            make_issue(
                rule_id=(
                    "METRIC_TABLE"
                ),

                title=(
                    "Metric Source Table "
                    "与 SQL 不一致"
                ),

                severity=(
                    Severity.HIGH
                ),

                message=(
                    f"Metric {metric.name!r} "
                    "要求使用 Approved "
                    "Source Table "
                    f"{metric.table!r}，"
                    "但当前 SQL 未读取该表。"
                ),

                suggestion=(
                    "检查 SQL 是否使用了"
                    "该 Metric 已批准的"
                    "物理来源表。"
                ),

                evidence=(
                    f"metric={metric.name}; "
                    f"expected_table="
                    f"{metric.table}; "
                    f"sql_source_tables="
                    f"{_format_source_tables(facts)}"
                ),

                category="semantic",

                action=(
                    METRIC_TABLE_ACTION
                ),

                auto_fixable=False,
            )
        )

    return issues


# ============================================================
# Rule 3
# Metric → Aggregation
# ============================================================

def check_metric_aggregation(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:
    """
    仅检查已经拥有：

        aggregation
        +
        source_column

    的 Simple Metric。

    Expression-only Complex Metric
    当前 not_applicable。

    不重新解析 SemanticMetric.expression。
    """

    _ = sql

    facts = context.sql_facts

    if (
        facts is None
        or context.trust_evidence
        is None
    ):
        return []

    issues: list[Issue] = []

    for metric in (
        _selected_metrics(
            context
        )
    ):

        if (
            metric.aggregation
            is None
            or metric.source_column
            is None
        ):
            continue

        expected_function = (
            _normalize_name(
                metric.aggregation
            )
        )

        expected_column = (
            _normalize_name(
                metric.source_column
            )
        )

        matched = any(
            (
                _normalize_name(
                    aggregate.function
                )
                == expected_function
                and aggregate.column
                is not None
                and _normalize_name(
                    aggregate.column.name
                )
                == expected_column
            )
            for aggregate
            in facts.aggregate_facts
        )

        if matched:
            continue

        issues.append(
            make_issue(
                rule_id=(
                    "METRIC_AGGREGATION"
                ),

                title=(
                    "Metric Aggregation "
                    "与 SQL 不一致"
                ),

                severity=(
                    Severity.HIGH
                ),

                message=(
                    f"Metric {metric.name!r} "
                    "要求 "
                    f"{expected_function}"
                    f"({expected_column})，"
                    "当前 SQL 未找到"
                    "对应的确定性聚合事实。"
                ),

                suggestion=(
                    "检查 SQL 的聚合函数"
                    "和聚合字段是否与"
                    "Approved Metric 一致。"
                ),

                evidence=(
                    f"metric={metric.name}; "
                    f"expected="
                    f"{expected_function}"
                    f"({expected_column}); "
                    f"actual="
                    f"{_format_aggregate_facts(facts)}"
                ),

                category="semantic",

                action=(
                    METRIC_AGGREGATION_ACTION
                ),

                auto_fixable=False,
            )
        )

    return issues


# ============================================================
# Rule 4
# Metric → Fixed Filter
# ============================================================

def check_metric_fixed_filter(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:
    """
    Approved Semantic Filter
        vs
    SQLFacts.predicate_facts

    当前阶段只检查 SQLFacts
    能形式化表达的简单 Predicate。

    首轮为 ADVISORY，
    后续根据 Evaluation 决定
    是否具备升级 BLOCK 的证明强度。
    """

    _ = sql

    facts = context.sql_facts

    if (
        facts is None
        or context.trust_evidence
        is None
    ):
        return []

    issues: list[Issue] = []

    for metric in (
        _selected_metrics(
            context
        )
    ):

        for semantic_filter in (
            metric.fixed_filters
        ):

            expected_operator = (
                _normalize_filter_operator(
                    semantic_filter.operator
                )
            )

            # SQLFacts 当前不支持的
            # Operator：
            #
            # Evidence 不充分，
            # 不制造“缺失”结论。
            if expected_operator is None:
                continue

            if any(
                _predicate_matches_filter(
                    predicate,
                    semantic_filter,
                )
                for predicate
                in facts.predicate_facts
            ):
                continue

            issues.append(
                make_issue(
                    rule_id=(
                        "METRIC_FIXED_FILTER"
                    ),

                    title=(
                        "Metric Fixed Filter "
                        "未被 SQL 可靠落实"
                    ),

                    severity=(
                        Severity.HIGH
                    ),

                    message=(
                        f"Metric {metric.name!r} "
                        "要求固定过滤条件 "
                        f"{semantic_filter.column} "
                        f"{semantic_filter.operator} "
                        f"{semantic_filter.value!r}，"
                        "当前 SQLFacts 中"
                        "未找到等价的简单 Predicate。"
                    ),

                    suggestion=(
                        "检查 SQL 是否落实"
                        "Approved Metric 的"
                        "固定过滤条件。"
                    ),

                    evidence=(
                        f"metric={metric.name}; "
                        f"expected_filter="
                        f"{semantic_filter.column}:"
                        f"{expected_operator}:"
                        f"{semantic_filter.value!r}; "
                        f"predicate_facts="
                        f"{facts.predicate_facts!r}"
                    ),

                    category="semantic",

                    action=(
                        METRIC_FIXED_FILTER_ACTION
                    ),

                    auto_fixable=False,
                )
            )

    return issues


# ============================================================
# Rule 5
# Partition Constraint
# ============================================================

def check_partition_constraint(
    sql: str,
    context: ReviewContext,
) -> list[Issue]:
    """
    Applicability Evidence：

    LinkedSchema
        ↓
    当前任务实际绑定的 Physical Table

    TableMetadata.partition_fields
        ↓
    该表是否明确声明 Partition

    SQLFacts.predicate_facts
        ↓
    SQL 是否对 Partition Field
    有可确定识别的 WHERE Predicate

    无 partition declaration
    → not_applicable
    """

    _ = sql

    facts = context.sql_facts

    evidence = (
        context.trust_evidence
    )

    if (
        facts is None
        or evidence is None
    ):
        return []

    issues: list[Issue] = []

    for linked_table in (
        evidence
        .linked_schema
        .tables
    ):

        metadata = (
            linked_table.metadata
        )

        if not (
            metadata.partition_fields
        ):
            continue

        # 如果 SQL 根本没读该表，
        # METRIC_TABLE / 其它 Table Rule
        # 已经负责。
        #
        # Partition Rule 不制造重复问题。
        if not any(
            _table_matches(
                source_table,
                metadata.full_name,
            )
            for source_table
            in facts.source_tables
        ):
            continue

        status = (
            _partition_constraint_status(
                facts=facts,
                physical_table=(
                    metadata.full_name
                ),
                partition_fields=(
                    metadata
                    .partition_fields
                ),
            )
        )

        # True：
        # 已证明存在 constraint。
        #
        # None：
        # 当前 SQL Evidence 不足，
        # 不能安全判断。
        if status is not False:
            continue

        issues.append(
            make_issue(
                rule_id=(
                    "PARTITION_CONSTRAINT"
                ),

                title=(
                    "Partition Constraint "
                    "未被 SQL 可靠落实"
                ),

                severity=(
                    Severity.MEDIUM
                ),

                message=(
                    "当前 SQL 读取了"
                    f"分区表 "
                    f"{metadata.full_name!r}，"
                    "但未找到针对其"
                    "分区字段的确定性 Predicate。"
                ),

                suggestion=(
                    "确认该查询是否应"
                    "增加分区字段过滤条件。"
                ),

                evidence=(
                    f"table="
                    f"{metadata.full_name}; "
                    f"partition_fields="
                    f"{metadata.partition_fields}; "
                    f"predicate_facts="
                    f"{facts.predicate_facts!r}"
                ),

                category="semantic",

                action=(
                    PARTITION_CONSTRAINT_ACTION
                ),

                auto_fixable=False,
            )
        )

    return issues


# ============================================================
# Text-to-SQL Rule Pack
# ============================================================

TEXT_TO_SQL_RULES = [

    Rule(
        rule_id=(
            "TEXT_TO_SQL_READ_ONLY"
        ),

        name=(
            "Text-to-SQL read only"
        ),

        severity=Severity.HIGH,

        category="safety",

        description=(
            "Text-to-SQL "
            "只允许只读查询。"
        ),

        check=(
            check_text_to_sql_read_only
        ),

        modes={
            "debug",
            "prod",
            "backfill",
        },

        packs=frozenset(
            {
                "text_to_sql",
            }
        ),
    ),

    Rule(
        rule_id=(
            "METRIC_TABLE"
        ),

        name=(
            "Metric source table"
        ),

        severity=Severity.HIGH,

        category="semantic",

        description=(
            "ADVISORY rollout: "
            "SQL 应使用当前 Metric "
            "批准的 Source Table。"
        ),

        check=(
            check_metric_table
        ),

        modes={
            "debug",
            "prod",
            "backfill",
        },

        packs=frozenset(
            {
                "text_to_sql",
            }
        ),
    ),

    Rule(
        rule_id=(
            "METRIC_AGGREGATION"
        ),

        name=(
            "Metric aggregation"
        ),

        severity=Severity.HIGH,

        category="semantic",

        description=(
            "ADVISORY rollout: "
            "SQL 的简单聚合应与 "
            "Approved Metric 一致。"
        ),

        check=(
            check_metric_aggregation
        ),

        modes={
            "debug",
            "prod",
            "backfill",
        },

        packs=frozenset(
            {
                "text_to_sql",
            }
        ),
    ),

    Rule(
        rule_id=(
            "METRIC_FIXED_FILTER"
        ),

        name=(
            "Metric fixed filter"
        ),

        severity=Severity.HIGH,

        category="semantic",

        description=(
            "ADVISORY rollout: "
            "SQL 应落实 Approved Metric "
            "声明的固定过滤条件。"
        ),

        check=(
            check_metric_fixed_filter
        ),

        modes={
            "debug",
            "prod",
            "backfill",
        },

        packs=frozenset(
            {
                "text_to_sql",
            }
        ),
    ),

    Rule(
        rule_id=(
            "PARTITION_CONSTRAINT"
        ),

        name=(
            "Partition constraint"
        ),

        severity=Severity.MEDIUM,

        category="semantic",

        description=(
            "ADVISORY rollout: "
            "仅当 Physical Metadata "
            "明确声明分区字段时，"
            "检查 SQL 分区过滤 Evidence。"
        ),

        check=(
            check_partition_constraint
        ),

        modes={
            "debug",
            "prod",
            "backfill",
        },

        packs=frozenset(
            {
                "text_to_sql",
            }
        ),
    ),
]