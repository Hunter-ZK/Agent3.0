from __future__ import annotations

import argparse
import sys

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import (
    Node,
    to_node,
)
from sqlglot.optimizer import (
    build_scope,
    qualify,
)
from sqlglot.schema import (
    MappingSchema,
)

from sql_pilot_engine.analysis.sql_parser import (
    SQLParser,
)
from sql_pilot_engine.dialects.sqlglot import (
    resolve_sqlglot_dialect,
)
from sql_pilot_engine.evidence.program_metadata import (
    MetadataObjectRole,
    ProgramMetadataResolver,
    TableResolutionStatus,
)
from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)
from sql_pilot_engine.program.enums import (
    ProgramAnalysisStatus,
)
from sql_pilot_engine.program.models import (
    SQLProgram,
)
from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)


PUBLIC_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "sql_pilot_engine"
    / "tests"
    / "fixtures"
    / "simulation"
    / "maxcompute_production_shape.sql"
)


# ============================================================
# Public production-shape synthetic schema
#
# 这里只表达 tests/fixtures/simulation/
# maxcompute_production_shape.sql 中两个物理源表。
#
# 目标：
#   测 SQLGlot Lineage 能力。
#
# 不是：
#   模拟正式 Metadata。
# ============================================================

PUBLIC_SCHEMA: dict[
    str,
    dict[str, str],
] = {
    "fact_sales": {
        "customer_id": "string",
        "region": "string",
        "product": "string",
        "amount": "bigint",
        "tags": "string",
        "batch_num": "string",
        "dt": "string",
    },
    "dim_customer": {
        "customer_id": "string",
        "customer_name": "string",
    },
}


@dataclass(
    frozen=True,
    slots=True,
)
class PhysicalLeaf:
    """
    SQLGlot Lineage 最终到达的物理字段。

    这里只是 Spike 内部结构，
    不是正式 Lineage DTO。
    """

    table_name: str
    column_name: str

@dataclass(
    frozen=True,
    slots=True,
)
class ColumnSpikeResult:
    """
    一个顶层 projection 的 Lineage Spike 结果。

    注意：

    output_column 只是展示名称。

    真正稳定定位一个 projection 的是：

        statement_index
        +
        output_index

    因为合法 SQL projection
    不一定拥有 alias/name。
    """

    statement_index: int

    # 0-based projection position
    output_index: int

    # 有字段名/alias 时使用真实名字；
    # 没有时使用 __projection_N
    output_column: str

    # 保留投影 SQL，方便失败分析。
    projection_sql: str

    node_count: int

    physical_leaves: tuple[
        PhysicalLeaf,
        ...,
    ]

    unresolved_leaves: tuple[
        str,
        ...,
    ]

    other_terminals: tuple[
        str,
        ...,
    ]

    error_message: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class MetadataSchemaBuildResult:
    """
    Metadata → MappingSchema 的 Spike 结果。
    """

    schema: MappingSchema

    resolved_tables: tuple[
        str,
        ...,
    ]

    blocked_tables: tuple[
        str,
        ...,
    ]


def _identifier_tail(
    value: str,
) -> str:
    """
    从：

        fact_sales.amount
        "fact_sales"."amount"
        `fact_sales`.`amount`

    中取得最后一个 identifier。

    这里只用于 Spike 报告，
    不作为正式 SQL identifier parser。
    """

    value = (
        value
        .split(".")[-1]
        .strip()
    )

    return (
        value
        .strip(
            '`"[]'
        )
        .lower()
    )


def _extract_query(
    expression: exp.Expression,
) -> exp.Query | None:
    """
    从一条 SQL Statement 中取得真正进行
    Column Lineage 的 Query。

    SQLGlot lineage() 要求输入 SELECT / Query，
    而 production.sql 的顶层是：

        INSERT OVERWRITE ...

    所以必须从 Insert 中取得它的 query expression。


    特别注意 WITH：

        WITH a AS (...)
        INSERT ...
        SELECT ...

    SQLGlot 可能把 WITH 挂在 Insert 上，
    而不是内部 SELECT 上。

    因此这里把 WITH 复制回 Query，
    保证 CTE DAG 不丢。
    """

    if isinstance(
        expression,
        exp.Query,
    ):
        return expression.copy()

    if not isinstance(
        expression,
        exp.Insert,
    ):
        return None

    query = expression.args.get(
        "expression"
    )

    if not isinstance(
        query,
        exp.Query,
    ):
        return None

    query = query.copy()

    statement_with = (
        expression.args.get(
            "with_"
        )
    )

    query_with = (
        query.args.get(
            "with_"
        )
    )

    if (
        statement_with is not None
        and query_with is None
    ):
        query.set(
            "with_",
            statement_with.copy(),
        )

    return query




def _physical_table_name(
    table: exp.Table,
    *,
    dialect: str,
) -> str:
    """
    使用 SQLGlot 自己的 table_name()，
    不手工拼 db/table。
    """

    name = exp.table_name(
        table,
        dialect=dialect,
    )

    return (
        name
        .strip()
        .lower()
    )


def _inspect_lineage_node(
    node: Node,
    *,
    dialect: str,
) -> tuple[
    int,
    tuple[PhysicalLeaf, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    """
    将 SQLGlot Lineage Graph 的终点分类。

    终点分三类：

    1. exp.Table
       → 已追到物理表。

    2. exp.Placeholder
       → SQLGlot 无法确定 source。

    3. 其它 terminal
       → 可能是常量表达式等，
          不能自动当成 lineage failure。
    """

    walked_nodes = tuple(
        node.walk()
    )

    physical: set[
        PhysicalLeaf
    ] = set()

    unresolved: set[str] = set()

    other: set[str] = set()

    for item in walked_nodes:

        if item.downstream:
            continue

        expression = (
            item.expression
        )

        if isinstance(
            expression,
            exp.Table,
        ):
            physical.add(
                PhysicalLeaf(
                    table_name=(
                        _physical_table_name(
                            expression,
                            dialect=dialect,
                        )
                    ),
                    column_name=(
                        _identifier_tail(
                            item.name
                        )
                    ),
                )
            )

            continue

        if isinstance(
            expression,
            exp.Placeholder,
        ):
            unresolved.add(
                item.name
            )

            continue

        other.add(
            item.name
        )

    return (
        len(walked_nodes),

        tuple(
            sorted(
                physical,
                key=lambda item: (
                    item.table_name,
                    item.column_name,
                ),
            )
        ),

        tuple(
            sorted(
                unresolved
            )
        ),

        tuple(
            sorted(
                other
            )
        ),
    )

def _trace_statement(
    *,
    statement_index: int,
    expression: exp.Expression,
    schema: MappingSchema,
    dialect: str,
) -> tuple[
    ColumnSpikeResult,
    ...,
]:
    """
    对一条 Statement 的全部最终 projection
    执行 Column Lineage。

    与旧实现不同：

    旧：
        projection name
            ↓
        lineage(name)

    新：
        projection position
            ↓
        qualify()
            ↓
        build_scope()
            ↓
        to_node(index)

    原因：

    合法 SQL projection
    不一定拥有 alias/name。

    示例：

        SELECT 1

        SELECT CURRENT_TIMESTAMP()

        SELECT (
            SELECT MAX(batch_num)
            FROM xxx
        )

    这些都必须能够进行 Lineage。
    """

    query = _extract_query(
        expression
    )

    if query is None:
        return ()

    # ==================================================
    # 1. Qualification
    #
    # lineage() convenience API 内部原本也会执行
    # qualify()。
    #
    # 现在我们因为需要 positional lineage，
    # 所以把这一步显式拿出来。
    # ==================================================

    try:

        qualified_query = (
            qualify.qualify(
                query.copy(),

                dialect=dialect,

                schema=schema,

                # 与 SQLGlot lineage()
                # v28.10.1 内部行为保持一致。
                validate_qualify_columns=False,

                identify=False,
            )
        )

    except Exception as exc:

        return (
            ColumnSpikeResult(
                statement_index=(
                    statement_index
                ),

                output_index=-1,

                output_column=(
                    "__qualification__"
                ),

                projection_sql="",

                node_count=0,

                physical_leaves=(),

                unresolved_leaves=(),

                other_terminals=(),

                error_message=(
                    "Qualification failed: "
                    f"{exc}"
                ),
            ),
        )

    # ==================================================
    # 2. Build SQLGlot Scope
    #
    # Scope 是 SQLGlot 的临时 Compiler Object。
    #
    # 它不进入 SQLProgram，
    # 也不进入正式 Agent Domain。
    # ==================================================

    scope = build_scope(
        qualified_query
    )

    if scope is None:

        return (
            ColumnSpikeResult(
                statement_index=(
                    statement_index
                ),

                output_index=-1,

                output_column=(
                    "__scope__"
                ),

                projection_sql="",

                node_count=0,

                physical_leaves=(),

                unresolved_leaves=(),

                other_terminals=(),

                error_message=(
                    "SQLGlot could not "
                    "build query scope."
                ),
            ),
        )

    # ==================================================
    # 3. Projection-by-projection lineage
    #
    # 这里不再调用：
    #
    #     lineage(column_name)
    #
    # 而直接：
    #
    #     to_node(index)
    #
    # 因此 unnamed projection
    # 不再是异常。
    # ==================================================

    results: list[
        ColumnSpikeResult
    ] = []

    projections = tuple(
        scope.expression.selects
    )

    for (
        output_index,
        projection,
    ) in enumerate(
        projections
    ):

        raw_name = (
            projection
            .alias_or_name
            .strip()
        )

        if raw_name:

            output_column = (
                raw_name.lower()
            )

        else:

            # 只是 Spike 报告显示名称。
            #
            # 绝不能把这个 synthetic name
            # 当成正式 Lineage target field。
            output_column = (
                "__projection_"
                f"{output_index + 1}"
            )

        projection_sql = (
            projection.sql(
                dialect=dialect,
                pretty=False,
            )
        )

        try:

            root = to_node(
                output_index,

                scope=scope,

                dialect=dialect,

                trim_selects=True,
            )

            (
                node_count,
                physical_leaves,
                unresolved_leaves,
                other_terminals,
            ) = (
                _inspect_lineage_node(
                    root,
                    dialect=dialect,
                )
            )

            results.append(
                ColumnSpikeResult(
                    statement_index=(
                        statement_index
                    ),

                    output_index=(
                        output_index
                    ),

                    output_column=(
                        output_column
                    ),

                    projection_sql=(
                        projection_sql
                    ),

                    node_count=(
                        node_count
                    ),

                    physical_leaves=(
                        physical_leaves
                    ),

                    unresolved_leaves=(
                        unresolved_leaves
                    ),

                    other_terminals=(
                        other_terminals
                    ),
                )
            )

        except Exception as exc:

            results.append(
                ColumnSpikeResult(
                    statement_index=(
                        statement_index
                    ),

                    output_index=(
                        output_index
                    ),

                    output_column=(
                        output_column
                    ),

                    projection_sql=(
                        projection_sql
                    ),

                    node_count=0,

                    physical_leaves=(),

                    unresolved_leaves=(),

                    other_terminals=(),

                    error_message=str(
                        exc
                    ),
                )
            )

    return tuple(
        results
    )

def _mapping_schema(
    table_schemas: dict[
        str,
        dict[
            str,
            str | None,
        ],
    ],
    *,
    dialect: str,
) -> MappingSchema:
    """
    Agent-side table schema
        ↓
    SQLGlot MappingSchema

    支持：

        table

        db.table

        catalog.db.table

    但同一个 Spike 中，
    所有物理表必须使用一致 identity depth。

    AUTHORITATIVE Metadata 本来就应该做到这一点。
    """

    if not table_schemas:
        return MappingSchema(
            {},
            dialect=dialect,
        )

    depths = {
        len(
            name.split(".")
        )
        for name
        in table_schemas
    }

    if len(depths) != 1:
        raise ValueError(
            "Lineage Spike found mixed "
            "physical table identity depth: "
            f"{sorted(depths)!r}. "
            "This should be classified as "
            "a Metadata identity problem, "
            "not a Program lineage problem."
        )

    depth = next(
        iter(depths)
    )

    if depth < 1 or depth > 3:
        raise ValueError(
            "SQLGlot MappingSchema "
            "supports table identity "
            "depth 1-3 in this Spike."
        )

    mapping: dict = {}

    for (
        table_name,
        columns,
    ) in table_schemas.items():

        parts = (
            table_name.split(".")
        )

        if depth == 1:

            mapping[
                parts[0]
            ] = columns

        elif depth == 2:

            database = (
                parts[0]
            )

            table = (
                parts[1]
            )

            mapping.setdefault(
                database,
                {},
            )[
                table
            ] = columns

        else:

            catalog = (
                parts[0]
            )

            database = (
                parts[1]
            )

            table = (
                parts[2]
            )

            mapping.setdefault(
                catalog,
                {},
            ).setdefault(
                database,
                {},
            )[
                table
            ] = columns

    return MappingSchema(
        mapping,
        dialect=dialect,
    )


def _public_schema(
    *,
    dialect: str,
) -> MetadataSchemaBuildResult:

    schema = _mapping_schema(
        {
            table: {
                column: data_type
                for (
                    column,
                    data_type,
                )
                in columns.items()
            }
            for (
                table,
                columns,
            )
            in PUBLIC_SCHEMA.items()
        },
        dialect=dialect,
    )

    return MetadataSchemaBuildResult(
        schema=schema,

        resolved_tables=tuple(
            sorted(
                PUBLIC_SCHEMA
            )
        ),

        blocked_tables=(),
    )


def _metadata_schema(
    *,
    program: SQLProgram,
    database_path: Path,
    dialect: str,
) -> MetadataSchemaBuildResult:
    """
    使用现有 Metadata Evidence Resolver：

        Program
          ↓
        exact table resolution
          ↓
        TableMetadata
          ↓
        MappingSchema

    这里绝对不重新实现：

        bare table fallback
        fuzzy matching
        identifier disambiguation

    因为这些已经属于
    ProgramMetadataResolver 的职责。
    """

    repository = (
        SQLiteMetadataRepository(
            database_path
        )
    )

    evidence = ProgramMetadataResolver(
        provider=repository,
        catalog=repository,
    ).resolve(
        program
    )

    table_schemas: dict[
        str,
        dict[
            str,
            str | None,
        ],
    ] = {}

    resolved: list[str] = []

    blocked: list[str] = []

    for table in evidence.tables:

        if (
            table.role
            is not
            MetadataObjectRole.READ_SOURCE
        ):
            continue

        if (
            table.status
            is not
            TableResolutionStatus.RESOLVED
            or table.metadata is None
        ):
            blocked.append(
                (
                    f"{table.requested_table}"
                    f" [{table.status.value}]"
                )
            )

            continue

        # MappingSchema 的 key 必须与 SQL
        # 中出现的 physical identifier 一致。
        #
        # bare SQL name 若已经被 Resolver
        # 唯一解析，也仍使用 requested_table。
        schema_key = (
            table
            .requested_table
            .lower()
        )

        columns: dict[
            str,
            str | None,
        ] = {}

        for column in (
            table
            .metadata
            .columns
            .values()
        ):

            data_type = (
                column
                .technical
                .data_type
                .strip()
            )

            # PARTIAL Metadata 可能没有类型。
            #
            # MappingSchema 这里使用 None，
            # 表示 UNKNOWN。
            #
            # 绝不猜 STRING。
            columns[
                column.name
            ] = (
                data_type
                if data_type
                else None
            )

        if not columns:

            blocked.append(
                (
                    f"{table.requested_table}"
                    " [no columns]"
                )
            )

            continue

        table_schemas[
            schema_key
        ] = columns

        resolved.append(
            schema_key
        )

    schema = _mapping_schema(
        table_schemas,
        dialect=dialect,
    )

    return MetadataSchemaBuildResult(
        schema=schema,

        resolved_tables=tuple(
            sorted(
                resolved
            )
        ),

        blocked_tables=tuple(
            sorted(
                blocked
            )
        ),
    )


def _feature_counts(
    expressions: tuple[
        exp.Expression,
        ...,
    ],
) -> Counter[str]:
    """
    不依赖特定 Expression Class 名字，
    直接按 SQLGlot node.key 做 Spike 统计。
    """

    result: Counter[str] = (
        Counter()
    )

    for expression in expressions:

        for node in expression.walk():

            result[
                node.key.lower()
            ] += 1

    return result


def _analyze_program(
    sql: str,
) -> SQLProgram:

    result = (
        ProgramAnalysisService()
        .analyze(
            sql,
            dialect="maxcompute",
        )
    )

    print()
    print(
        "=== Program Analysis ==="
    )

    print(
        f"status: "
        f"{result.status.value}"
    )

    if result.diagnostics:

        print(
            "diagnostics:"
        )

        for item in (
            result.diagnostics
        ):
            print(
                f"  - {item}"
            )

    if (
        result.status
        is ProgramAnalysisStatus.FAILED
        or result.program is None
    ):
        raise RuntimeError(
            "Program Analysis failed: "
            f"{result.failure_reason}"
        )

    program = (
        result.program
    )

    print(
        f"statements: "
        f"{len(program.statements)}"
    )

    print(
        f"cte_nodes: "
        f"{len(program.cte_nodes)}"
    )

    print(
        f"scope_analyses: "
        f"{len(program.scope_analyses)}"
    )

    return program


def _parse_program_statements(
    program: SQLProgram,
) -> tuple[
    exp.Expression,
    ...,
]:

    parser = SQLParser()

    expressions: list[
        exp.Expression
    ] = []

    for statement in (
        program.statements
    ):

        result = parser.parse(
            statement.normalized_sql,
            dialect="maxcompute",
        )

        if (
            not result.success
            or len(result.statements)
            != 1
        ):
            raise RuntimeError(
                "Lineage Spike could not "
                "reparse SQLStatement "
                f"{statement.index}: "
                f"{result.error_message}"
            )

        expressions.append(
            result.statements[0]
        )

    return tuple(
        expressions
    )


def _print_features(
    expressions: tuple[
        exp.Expression,
        ...,
    ],
) -> None:

    counts = _feature_counts(
        expressions
    )

    print()
    print(
        "=== Structural Features ==="
    )

    for feature in (
        "cte",
        "lateral",
        "union",
        "groupingsets",
        "insert",
    ):
        print(
            f"{feature}: "
            f"{counts.get(feature, 0)}"
        )


def _print_metadata_schema(
    result: MetadataSchemaBuildResult,
) -> None:

    print()
    print(
        "=== Metadata Schema ==="
    )

    print(
        "resolved physical tables: "
        f"{len(result.resolved_tables)}"
    )

    for table in (
        result.resolved_tables
    ):
        print(
            f"  RESOLVED  {table}"
        )

    print(
        "blocked physical tables: "
        f"{len(result.blocked_tables)}"
    )

    for table in (
        result.blocked_tables
    ):
        print(
            f"  BLOCKED   {table}"
        )

def _print_lineage(
    results: tuple[
        ColumnSpikeResult,
        ...,
    ],
) -> None:

    print()
    print(
        "=== Column Lineage ==="
    )

    for result in results:

        print()

        print(
            f"[statement "
            f"{result.statement_index} "
            f"projection "
            f"{result.output_index}] "
            f"{result.output_column}"
        )

        if result.projection_sql:

            print(
                "  projection:"
            )

            print(
                "    "
                + result
                .projection_sql
                .replace(
                    "\n",
                    "\n    ",
                )
            )

        if (
            result.error_message
            is not None
        ):

            print(
                "  ERROR: "
                f"{result.error_message}"
            )

            continue

        print(
            f"  nodes: "
            f"{result.node_count}"
        )

        if (
            result.physical_leaves
        ):

            print(
                "  physical leaves:"
            )

            for leaf in (
                result
                .physical_leaves
            ):

                print(
                    "    "
                    f"{leaf.table_name}."
                    f"{leaf.column_name}"
                )

        if (
            result.unresolved_leaves
        ):

            print(
                "  unresolved leaves:"
            )

            for leaf in (
                result
                .unresolved_leaves
            ):

                print(
                    f"    {leaf}"
                )

        if (
            result.other_terminals
        ):

            print(
                "  other terminals:"
            )

            for leaf in (
                result
                .other_terminals
            ):

                print(
                    f"    {leaf}"
                )


def _public_gate(
    results: tuple[
        ColumnSpikeResult,
        ...,
    ],
) -> tuple[
    bool,
    tuple[str, ...],
]:
    """
    Public production-shape 的最小架构证据。

    三个关键字段：

    region
        验证普通 CTE + UNION。

    total_amount
        验证多层聚合 +
        GROUPING SETS。

    tag
        验证 LATERAL VIEW EXPLODE。
    """

    failures: list[str] = []

    by_key = {
        (
            result.statement_index,
            result.output_column,
        ): result
        for result
        in results
    }

    expected = {
        (
            0,
            "region",
        ): PhysicalLeaf(
            table_name="fact_sales",
            column_name="region",
        ),

        (
            0,
            "total_amount",
        ): PhysicalLeaf(
            table_name="fact_sales",
            column_name="amount",
        ),

        (
            1,
            "tag",
        ): PhysicalLeaf(
            table_name="fact_sales",
            column_name="tags",
        ),
    }

    for (
        key,
        expected_leaf,
    ) in expected.items():

        result = by_key.get(
            key
        )

        if result is None:

            failures.append(
                "Missing lineage result: "
                f"{key}"
            )

            continue

        if (
            result.error_message
            is not None
        ):

            failures.append(
                "Lineage error "
                f"{key}: "
                f"{result.error_message}"
            )

            continue

        if (
            expected_leaf
            not in result.physical_leaves
        ):

            failures.append(
                f"{key} does not reach "
                f"{expected_leaf.table_name}."
                f"{expected_leaf.column_name}; "
                "actual="
                f"{result.physical_leaves!r}"
            )

    return (
        not failures,
        tuple(failures),
    )


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Agent3.0 one-off "
            "Column Lineage architecture Spike."
        )
    )

    parser.add_argument(
        "--mode",
        choices=(
            "public",
            "private",
        ),
        required=True,
    )

    parser.add_argument(
        "--sql",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--metadata-db",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    if (
        args.mode
        == "public"
    ):

        sql_path = (
            args.sql
            or PUBLIC_FIXTURE
        )

    else:

        if args.sql is None:

            parser.error(
                "--sql is required "
                "for private mode."
            )

        if (
            args.metadata_db
            is None
        ):

            parser.error(
                "--metadata-db is required "
                "for private mode."
            )

        sql_path = args.sql

    raw_sql = (
        sql_path.read_text(
            encoding="utf-8"
        )
    )

    print(
        "Lineage Spike"
    )

    print(
        "=" * 70
    )

    print(
        f"mode: "
        f"{args.mode}"
    )

    print(
        f"sql: "
        f"{sql_path}"
    )

    program = (
        _analyze_program(
            raw_sql
        )
    )

    expressions = (
        _parse_program_statements(
            program
        )
    )

    _print_features(
        expressions
    )

    read_dialect = (
        resolve_sqlglot_dialect(
            "maxcompute"
        )
    )

    if (
        args.mode
        == "public"
    ):

        schema_result = (
            _public_schema(
                dialect=(
                    read_dialect
                )
            )
        )

    else:

        assert (
            args.metadata_db
            is not None
        )

        schema_result = (
            _metadata_schema(
                program=program,

                database_path=(
                    args.metadata_db
                ),

                dialect=(
                    read_dialect
                ),
            )
        )

    _print_metadata_schema(
        schema_result
    )

    # Private Lineage 依赖完整 Metadata。
    #
    # Metadata 尚未准备好时直接结束，
    # 不继续执行 qualification / lineage，
    # 避免产生误导性的下游字段错误。
    if (
        args.mode == "private"
        and schema_result.blocked_tables
    ):
        print()
        print("=== Verdict ===")
        print(
            "PRIVATE LINEAGE SPIKE: "
            "METADATA_BLOCKED"
        )
        print(
            "Program structure is valid. "
            "Authoritative physical lineage "
            "is deferred until Metadata "
            "is available."
        )

        return 2

    lineage_results: list[
        ColumnSpikeResult
    ] = []

    for (
        statement_index,
        expression,
    ) in enumerate(
        expressions
    ):

        lineage_results.extend(
            _trace_statement(
                statement_index=(
                    statement_index
                ),

                expression=expression,

                schema=(
                    schema_result
                    .schema
                ),

                dialect=(
                    read_dialect
                ),
            )
        )

    final_results = tuple(
        lineage_results
    )

    _print_lineage(
        final_results
    )

    print()
    print(
        "=== Verdict ==="
    )

    if (
        args.mode
        == "public"
    ):

        (
            passed,
            failures,
        ) = _public_gate(
            final_results
        )

        if passed:

            print(
                "PUBLIC LINEAGE SPIKE: PASS"
            )

            print(
                "Current Program Contract "
                "shows no structural gap "
                "for the public "
                "production-shape fixture."
            )

            return 0

        print(
            "PUBLIC LINEAGE SPIKE: FAIL"
        )

        for failure in failures:

            print(
                f"  - {failure}"
            )

        return 1

    # ------------------------------------------------------
    # Private Gate
    # ------------------------------------------------------


    lineage_errors = tuple(
        result
        for result
        in final_results
        if (
            result.error_message
            is not None
            or result.unresolved_leaves
        )
    )

    if lineage_errors:

        print(
            "PRIVATE LINEAGE SPIKE: FAIL"
        )

        print(
            "Metadata is resolved, "
            "but SQLGlot lineage still "
            "contains errors/unresolved "
            "leaves."
        )

        return 1

    print(
        "PRIVATE LINEAGE SPIKE: PASS"
    )

    print(
        "No evidence currently requires "
        "changing SQLProgram for Lineage."
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )