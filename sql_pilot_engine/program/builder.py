from __future__ import annotations

from collections import defaultdict

from sqlglot import exp

from sql_pilot_engine.analysis.sql_parser import (
    SQLParseResult,
)
from sql_pilot_engine.dialects.sqlglot import (
    resolve_sqlglot_dialect,
)
from sql_pilot_engine.program.enums import (
    StatementKind,
    WriteStrategy,
)
from sql_pilot_engine.program.models import (
    CTENode,
    ParameterBinding,
    ParameterOccurrence,
    PartitionBinding,
    ProgramPreprocessResult,
    SQLProgram,
    SQLStatement,
    WriteTarget,
)


class ProgramBuilder:
    """
    SQLGlot AST → SQLProgram 的结构投影器。

    【架构位置】

        ProgramPreprocessResult
                +
        SQLParseResult
                ↓
          ProgramBuilder
                ↓
            SQLProgram

    Builder 只负责确定性的结构转换。

    当前不负责：

    - CTE dependency；
    - Scope SQLFacts；
    - Metadata；
    - Lineage；
    - Review；
    - Fix；
    - Execution。

    后续模块消费 SQLProgram，
    不应该重新从 Raw SQL 猜这些基础结构。
    """

    def build(
        self,
        *,
        preprocess_result: ProgramPreprocessResult,
        parse_result: SQLParseResult,
    ) -> SQLProgram:
        """
        根据已经成功解析的 AST 构造 SQLProgram。

        Parser failure 不属于 Builder 的正常输入。

        如果 Parser 没有形成可信 AST，
        Builder 不应该尝试通过字符串猜测 Program 结构。
        """

        if not parse_result.success:
            raise ValueError(
                "ProgramBuilder cannot build "
                "from a failed parse result."
            )

        if not parse_result.statements:
            raise ValueError(
                "ProgramBuilder requires "
                "at least one parsed statement."
            )

        read_dialect = (
            resolve_sqlglot_dialect(
                parse_result.dialect
            )
        )

        statements: list[
            SQLStatement
        ] = []

        cte_nodes: list[
            CTENode
        ] = []

        for (
            statement_index,
            expression,
        ) in enumerate(
            parse_result.statements
        ):
            statement_ctes = (
                self._extract_ctes(
                    expression=expression,
                    statement_index=(
                        statement_index
                    ),
                )
            )

            cte_nodes.extend(
                statement_ctes
            )

            statement = SQLStatement(
                index=statement_index,
                kind=(
                    self._classify_statement(
                        expression
                    )
                ),
                normalized_sql=(
                    expression.sql(
                        dialect=read_dialect
                    )
                ),
                write_target=(
                    self._extract_write_target(
                        expression=expression,
                        dialect=read_dialect,
                    )
                ),
                cte_names=tuple(
                    cte.name
                    for cte
                    in statement_ctes
                ),
            )

            statements.append(
                statement
            )

        parameters = (
            self._group_parameters(
                preprocess_result.parameters
            )
        )

        return SQLProgram(
            raw_sql=(
                preprocess_result.raw_sql
            ),
            normalized_sql=(
                preprocess_result
                .normalized_sql
            ),
            statements=tuple(
                statements
            ),
            session_hints=(
                preprocess_result
                .session_hints
            ),
            parameters=parameters,
            source_map=(
                preprocess_result
                .source_map
            ),
            cte_nodes=tuple(
                cte_nodes
            ),
        )

    @staticmethod
    def _classify_statement(
        expression: exp.Expression,
    ) -> StatementKind:
        """
        SQLGlot root expression → StatementKind。

        INSERT 必须在 Query 之前判断，
        避免未来 Expression 继承关系变化造成误分类。
        """

        if isinstance(
            expression,
            exp.Insert,
        ):
            if expression.args.get(
                "overwrite"
            ):
                return (
                    StatementKind
                    .INSERT_OVERWRITE
                )

            return (
                StatementKind
                .INSERT_INTO
            )

        if isinstance(
            expression,
            exp.Update,
        ):
            return StatementKind.UPDATE

        if isinstance(
            expression,
            exp.Delete,
        ):
            return StatementKind.DELETE

        if isinstance(
            expression,
            exp.Merge,
        ):
            return StatementKind.MERGE

        if isinstance(
            expression,
            exp.Create,
        ):
            return StatementKind.CREATE

        # SELECT / UNION / INTERSECT / EXCEPT
        # 等查询根节点都属于 Query。
        if isinstance(
            expression,
            exp.Query,
        ):
            return StatementKind.SELECT

        return StatementKind.OTHER

    @classmethod
    def _extract_write_target(
        cls,
        *,
        expression: exp.Expression,
        dialect: str,
    ) -> WriteTarget | None:
        """
        当前 B2 只抽取 INSERT 写入目标。

        SQLGlot 28 的 Hive parser 会把：

            INSERT OVERWRITE TABLE db.t
            PARTITION(dt='202609')

        解析为：

            Insert
            ├── overwrite=True
            └── this=Table(...)
                    └── partition=Partition(...)

        因此这里直接读取 AST，
        不通过 regex 或字符串切割重新解释 SQL。
        """

        if not isinstance(
            expression,
            exp.Insert,
        ):
            return None

        target_expression = (
            expression.this
        )

        # INSERT INTO t(a, b)
        #
        # SQLGlot 可能把目标包装成：
        #
        #     Schema(
        #         this=Table(...),
        #         expressions=[...]
        #     )
        if isinstance(
            target_expression,
            exp.Schema,
        ):
            target_expression = (
                target_expression.this
            )

        if not isinstance(
            target_expression,
            exp.Table,
        ):
            return None

        table_name = (
            exp.table_name(
                target_expression,
                dialect=dialect,
            )
        )

        if not table_name:
            return None

        strategy = (
            WriteStrategy.OVERWRITE
            if expression.args.get(
                "overwrite"
            )
            else WriteStrategy.APPEND
        )

        partition_spec = (
            cls._extract_partition_spec(
                table=target_expression,
                dialect=dialect,
            )
        )

        return WriteTarget(
            table_name=table_name,
            strategy=strategy,
            partition_spec=(
                partition_spec
            ),
        )

    @classmethod
    def _extract_partition_spec(
        cls,
        *,
        table: exp.Table,
        dialect: str,
    ) -> tuple[
        PartitionBinding,
        ...,
    ]:
        """
        从 INSERT 目标 Table 中抽取 PARTITION(...)。

        支持：

            PARTITION(dt='202609')

        和：

            PARTITION(dt)

        也支持混合形式：

            PARTITION(
                year='2026',
                month
            )
        """

        partition = (
            table.args.get(
                "partition"
            )
        )

        if not isinstance(
            partition,
            exp.Partition,
        ):
            return ()

        bindings: list[
            PartitionBinding
        ] = []

        for item in (
            partition.expressions
        ):
            if isinstance(
                item,
                exp.EQ,
            ):
                name = (
                    cls._expression_name(
                        item.this,
                        dialect=dialect,
                    )
                )

                value_expression = (
                    item.expression
                )

                value = (
                    value_expression.sql(
                        dialect=dialect
                    )
                    if isinstance(
                        value_expression,
                        exp.Expression,
                    )
                    else str(
                        value_expression
                    )
                )

                bindings.append(
                    PartitionBinding(
                        name=name,
                        value=value,
                    )
                )

                continue

            # 没有 "=" 的 partition field
            # 代表动态分区。
            bindings.append(
                PartitionBinding(
                    name=(
                        cls._expression_name(
                            item,
                            dialect=dialect,
                        )
                    ),
                    value=None,
                )
            )

        return tuple(
            bindings
        )

    @staticmethod
    def _expression_name(
        expression: object,
        *,
        dialect: str,
    ) -> str:
        """
        从简单 AST expression 中取得稳定名称。

        Identifier / Column 等 SQLGlot 节点均提供 name。

        如果遇到其它合法 expression，
        最后退回 AST 自己的 SQL rendering，
        而不是自己解析字符串。
        """

        if isinstance(
            expression,
            exp.Expression,
        ):
            name = (
                expression.name
            )

            if name:
                return name

            return expression.sql(
                dialect=dialect
            )

        return str(
            expression
        )

    @staticmethod
    def _extract_ctes(
        *,
        expression: exp.Expression,
        statement_index: int,
    ) -> tuple[
        CTENode,
        ...,
    ]:
        """
        抽取 Statement 内所有 CTE。

        B2 当前只建立：
            name
            statement_index
            scope_id

        dependencies 暂时为空。

        CTE → CTE dependency 属于后续 B4，
        不能在 Builder 中顺手做掉。
        """

        nodes: list[
            CTENode
        ] = []

        for (
            cte_index,
            cte,
        ) in enumerate(
            expression.find_all(
                exp.CTE
            )
        ):
            name = (
                cte.alias_or_name
                .strip()
            )

            if not name:
                continue

            scope_id = (
                "statement:"
                f"{statement_index}:"
                "cte:"
                f"{cte_index}:"
                f"{name}"
            )

            nodes.append(
                CTENode(
                    name=name,
                    statement_index=(
                        statement_index
                    ),
                    scope_id=scope_id,
                )
            )

        return tuple(
            nodes
        )

    @staticmethod
    def _group_parameters(
        occurrences: tuple[
            ParameterOccurrence,
            ...,
        ],
    ) -> tuple[
        ParameterBinding,
        ...,
    ]:
        """
        occurrence-level 参数 → Program-level 参数。

        例如：

            ${p_month}
            ${p_month}
            ${p_month}

        A1：
            3 ParameterOccurrence

        B2：
            1 ParameterBinding
            occurrences = 3

        Program 层只聚合同名参数的 occurrence。
        参数用途不属于 SQLProgram Contract。
        """

        grouped: dict[
            str,
            list[
                ParameterOccurrence
            ],
        ] = defaultdict(
            list
        )

        ordered_names: list[
            str
        ] = []

        for occurrence in occurrences:
            if (
                occurrence.name
                not in grouped
            ):
                ordered_names.append(
                    occurrence.name
                )

            grouped[
                occurrence.name
            ].append(
                occurrence
            )

        return tuple(
            ParameterBinding(
                name=name,
                occurrences=tuple(
                    grouped[name]
                ),
            )
            for name
            in ordered_names
        )