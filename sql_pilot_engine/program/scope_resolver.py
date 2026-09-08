from __future__ import annotations

from dataclasses import replace

from sqlglot import exp
from sqlglot.optimizer.scope import (
    Scope,
    traverse_scope,
)

from sql_pilot_engine.analysis.facts import (
    ColumnReference,
    SQLFacts,
    TableReference,
)
from sql_pilot_engine.analysis.sql_parser import (
    SQLParseResult,
)
from sql_pilot_engine.program.models import (
    CTENode,
    ProgramScopeAnalysis,
    SQLProgram,
    ScopeSourceBinding,
    SourceBindingKind,
    ScopeOutputProjection,
)


def build_cte_expression_node_map(
    *,
    expression: exp.Expression,
    cte_nodes: tuple[
        CTENode,
        ...,
    ],
) -> dict[
    int,
    CTENode,
]:
    """
    建立：

        id(SQLGlot CTE query expression)
                    ↓
                CTENode

    ProgramBuilder、ScopeResolver 和
    CTEDependencyResolver 都基于同一份 AST。

    expression identity 因此可以作为分析过程内部
    的可靠桥接，不需要重新根据 CTE 名称猜测。
    """

    ctes = tuple(
        expression.find_all(
            exp.CTE
        )
    )

    if (
        len(ctes)
        != len(cte_nodes)
    ):
        raise ValueError(
            "Program CTE nodes are inconsistent "
            "with parsed CTE expressions."
        )

    return {
        id(cte.this): node
        for (
            cte,
            node,
        )
        in zip(
            ctes,
            cte_nodes,
            strict=True,
        )
    }

class ScopeResolver:
    """
    SQLGlot Scope → ProgramScopeAnalysis。

    【架构位置】

        SQLParser / SQLGlot AST
                ↓
        ProgramBuilder
                ↓
            SQLProgram
                ↓
          ScopeResolver
                ↓
        ProgramScopeAnalysis

    ScopeResolver 不实现自己的 Scope 算法。

    SQL 的：
    - CTE 边界；
    - subquery 边界；
    - derived table；
    - UNION scope；
    - source resolution；

    均由 SQLGlot Scope 提供。

    本类只负责把这些结构投影到 Agent3.0
    已有 SQLFacts / ProgramScopeAnalysis Contract。
    """

    def resolve(
        self,
        *,
        program: SQLProgram,
        parse_result: SQLParseResult,
    ) -> SQLProgram:
        if not parse_result.success:
            raise ValueError(
                "ScopeResolver cannot resolve "
                "a failed parse result."
            )

        if (
            len(program.statements)
            != len(parse_result.statements)
        ):
            raise ValueError(
                "SQLProgram statements and "
                "parsed statements are inconsistent."
            )

        analyses: list[
            ProgramScopeAnalysis
        ] = []

        for (
            statement_index,
            expression,
        ) in enumerate(
            parse_result.statements
        ):
            analyses.extend(
                self._resolve_statement(
                    statement_index=statement_index,
                    expression=expression,
                    cte_nodes=tuple(
                        node
                        for node
                        in program.cte_nodes
                        if (
                            node.statement_index
                            == statement_index
                        )
                    ),
                )
            )

        return replace(
            program,
            scope_analyses=tuple(
                analyses
            ),
        )

    def _resolve_statement(
        self,
        *,
        statement_index: int,
        expression: exp.Expression,
        cte_nodes: tuple[
            CTENode,
            ...,
        ],
    ) -> tuple[
        ProgramScopeAnalysis,
        ...,
    ]:
        """
        解析一条 Statement 内的全部 SQLGlot Scope。

        第一遍：
            给所有 Scope 建立稳定 scope_id。

        第二遍：
            生成 SQLFacts 和 ScopeSourceBinding。

        两遍处理的原因是：
            一个 Scope 的 source 可能指向
            当前 Statement 中另一个 Scope。
        """

        scopes = traverse_scope(
            expression
        )

        if not scopes:
            return ()

        cte_scope_mapping = (
            build_cte_expression_node_map(
                expression=expression,
                cte_nodes=cte_nodes,
            )
        )

        identified_scopes: list[
            tuple[
                Scope,
                str,
                str | None,
            ]
        ] = []

        scope_ids_by_expression: dict[
            int,
            str,
        ] = {}

        # --------------------------------------------------------
        # Pass 1:
        # SQLGlot Scope → Program scope_id
        # --------------------------------------------------------

        for (
            scope_index,
            scope,
        ) in enumerate(
            scopes
        ):
            (
                scope_id,
                cte_name,
            ) = self._identify_scope(
                statement_index=statement_index,
                scope_index=scope_index,
                scope=scope,
                cte_scope_mapping=(
                    cte_scope_mapping
                ),
            )

            identified_scopes.append(
                (
                    scope,
                    scope_id,
                    cte_name,
                )
            )

            scope_ids_by_expression[
                id(scope.expression)
            ] = scope_id

        # --------------------------------------------------------
        # Pass 2:
        # Scope facts + source bindings
        # --------------------------------------------------------

        analyses: list[
            ProgramScopeAnalysis
        ] = []

        for (
            scope,
            scope_id,
            cte_name,
        ) in identified_scopes:

            analyses.append(
                ProgramScopeAnalysis(
                    scope_id=scope_id,
                    statement_index=(
                        statement_index
                    ),
                    cte_name=cte_name,
                    facts=(
                        self._facts_from_scope(
                            scope
                        )
                    ),
                    source_bindings=(
                        self._source_bindings(
                            scope=scope,
                            scope_ids_by_expression=(
                                scope_ids_by_expression
                            ),
                        )
                    ),
                    output_projection=(
                        self._output_projection(
                            scope
                        )
                    ),
                )
            )

        return tuple(
            analyses
        )

    @staticmethod
    def _identify_scope(
        *,
        statement_index: int,
        scope_index: int,
        scope: Scope,
        cte_scope_mapping: dict[
            int,
            CTENode,
        ],
    ) -> tuple[
        str,
        str | None,
    ]:
        """
        为 SQLGlot Scope 分配 Agent3.0 scope_id。

        CTE：
            必须与 CTENode.scope_id 完全一致。

        Root：
            statement:{index}:root

        其它内部 Scope：
            statement:{index}:scope:{ordinal}:{type}
        """

        cte_node = (
            cte_scope_mapping.get(
                id(scope.expression)
            )
        )

        if cte_node is not None:
            return (
                cte_node.scope_id,
                cte_node.name,
            )

        if scope.is_root:
            return (
                (
                    "statement:"
                    f"{statement_index}:root"
                ),
                None,
            )

        scope_type = (
            scope.scope_type
            .name
            .lower()
        )

        return (
            (
                "statement:"
                f"{statement_index}:"
                "scope:"
                f"{scope_index}:"
                f"{scope_type}"
            ),
            None,
        )

    @classmethod
    def _source_bindings(
        cls,
        *,
        scope: Scope,
        scope_ids_by_expression: dict[
            int,
            str,
        ],
    ) -> tuple[
        ScopeSourceBinding,
        ...,
    ]:
        """
        将 SQLGlot selected_sources
        投影成 Agent3.0 的 source binding。

        这里刻意不重新解析 FROM/JOIN 文本。

        SQLGlot 已经完成：
            alias → Table / Scope

        我们只把第三方结构转换成
        Agent3.0 自己稳定的 Domain Contract。

        对当前明确无法映射的 Source：
            返回 UNRESOLVED。

        不通过 broad try/except
        把内部程序 Bug 伪装成 UNRESOLVED。
        """

        bindings: list[
            ScopeSourceBinding
        ] = []

        for (
            source_alias,
            (
                _,
                source,
            ),
        ) in (
            scope
            .selected_sources
            .items()
        ):
            alias = (
                str(source_alias)
                .strip()
                .lower()
            )

            # ----------------------------------------------------
            # Physical Table
            # ----------------------------------------------------

            if isinstance(
                source,
                exp.Table,
            ):
                bindings.append(
                    ScopeSourceBinding(
                        alias=alias,
                        kind=(
                            SourceBindingKind
                            .PHYSICAL_TABLE
                        ),
                        physical_table=(
                            cls
                            ._qualified_table_name(
                                source
                            )
                        ),
                    )
                )

                continue

            # ----------------------------------------------------
            # CTE / derived table / subquery Scope
            # ----------------------------------------------------

            if isinstance(
                source,
                Scope,
            ):
                source_scope_id = (
                    scope_ids_by_expression
                    .get(
                        id(
                            source.expression
                        )
                    )
                )

                if source_scope_id is None:
                    bindings.append(
                        ScopeSourceBinding(
                            alias=alias,
                            kind=(
                                SourceBindingKind
                                .UNRESOLVED
                            ),
                            unresolved_reason=(
                                "SQLGlot Scope source "
                                "could not be mapped to "
                                "a Program scope_id."
                            ),
                        )
                    )

                    continue

                bindings.append(
                    ScopeSourceBinding(
                        alias=alias,
                        kind=(
                            SourceBindingKind.SCOPE
                        ),
                        source_scope_id=(
                            source_scope_id
                        ),
                    )
                )

                continue

            # ----------------------------------------------------
            # Unknown SQLGlot source type
            #
            # 保留 alias，但明确降级。
            # ----------------------------------------------------

            bindings.append(
                ScopeSourceBinding(
                    alias=alias,
                    kind=(
                        SourceBindingKind
                        .UNRESOLVED
                    ),
                    unresolved_reason=(
                        "Unsupported SQLGlot "
                        "selected source type: "
                        f"{type(source).__name__}."
                    ),
                )
            )

        return tuple(
            bindings
        )

    @staticmethod
    def _output_projection(
        scope: Scope,
    ) -> ScopeOutputProjection:
        """
        提取当前 Scope 可以由 AST 确定的输出投影。

        这里只做结构事实，不做 schema inference。

        使用 SQLGlot projection.output_name：

        - SELECT a
            → "a"

        - SELECT a AS b
            → "b"

        - SELECT 1 + 2
            → ""

        因此不会通过 expression text
        猜一个并不存在的稳定列名。

        SELECT * / alias.*
        显式记录 wildcard，
        完整 schema 留给后续
        Execution Schema Propagation。
        """

        expression = (
            scope.expression
        )

        if not isinstance(
            expression,
            exp.Query,
        ):
            return (
                ScopeOutputProjection()
            )

        column_names: list[
            str
        ] = []

        has_wildcard = False

        unnamed_expression_count = 0

        for projection in (
            expression.selects
        ):
            # SQLGlot Expression.is_star
            # 同时覆盖：
            #
            #     *
            #     alias.*
            #
            # COUNT(*) 本身不是 projection star，
            # 所以不会被误判。
            if projection.is_star:
                has_wildcard = True
                continue

            output_name = (
                projection
                .output_name
                .strip()
                .lower()
            )

            if output_name:
                column_names.append(
                    output_name
                )

                continue

            unnamed_expression_count += 1

        return ScopeOutputProjection(
            column_names=tuple(
                column_names
            ),
            has_wildcard=(
                has_wildcard
            ),
            unnamed_expression_count=(
                unnamed_expression_count
            ),
        )

    @classmethod
    def _facts_from_scope(
        cls,
        scope: Scope,
    ) -> SQLFacts:
        """
        把 SQLGlot Scope 投影为现有 SQLFacts。

        重点：

        这里不能调用：

            SQLFactsExtractor.extract(
                SQLParseResult(
                    statements=[scope.expression]
                )
            )

        因为一个独立 CTE expression 已经脱离父级 WITH，
        单独扫描 exp.Table 会把其它 CTE 名称误判成物理表。

        Scope.selected_sources 已经完成：
            Physical Table
            vs
            CTE / Derived Scope

        的语义区分。
        """

        physical_sources: dict[
            str,
            exp.Table,
        ] = {}

        for (
            source_alias,
            (
                _,
                source,
            ),
        ) in (
            scope
            .selected_sources
            .items()
        ):
            if isinstance(
                source,
                exp.Table,
            ):
                physical_sources[
                    source_alias
                ] = source

        source_tables = {
            cls._qualified_table_name(
                table
            )
            for table
            in physical_sources.values()
        }

        table_references = {
            TableReference(
                physical_name=(
                    cls._qualified_table_name(
                        table
                    )
                ),
                alias=(
                    table.alias.lower()
                    if table.alias
                    else None
                ),
            )
            for table
            in physical_sources.values()
        }

        column_references = {
            ColumnReference(
                name=column.name.lower(),
                qualifier=(
                    column.table.lower()
                    if column.table
                    else None
                ),
            )
            for column
            in scope.columns
            if (
                column.name
                and column.name != "*"
            )
        }

        select_aliases = (
            cls._select_aliases(
                scope.expression
            )
        )

        cte_names = {
            cte.alias_or_name.lower()
            for cte
            in scope.ctes
            if cte.alias_or_name
        }

        statement_type = (
            scope.expression
            .key
            .lower()
        )

        return SQLFacts(
            statement_count=1,
            statement_types=(
                statement_type,
            ),
            source_tables=tuple(
                sorted(
                    source_tables
                )
            ),
            target_tables=(),
            insert_target_table=None,
            referenced_tables=tuple(
                sorted(
                    source_tables
                )
            ),
            cte_names=tuple(
                sorted(
                    cte_names
                )
            ),
            table_references=tuple(
                sorted(
                    table_references,
                    key=lambda item: (
                        item.physical_name,
                        item.alias or "",
                    ),
                )
            ),
            column_references=tuple(
                sorted(
                    column_references,
                    key=lambda item: (
                        item.qualifier or "",
                        item.name,
                    ),
                )
            ),
            select_aliases=tuple(
                sorted(
                    select_aliases
                )
            ),
            has_select_star=(
                cls._has_select_star(
                    scope.expression
                )
            ),
            has_drop=False,
            has_truncate=False,
            has_write_operation=False,
            has_partition_clause=False,
        )

    @staticmethod
    def _qualified_table_name(
        table: exp.Table,
    ) -> str:
        """
        保持与现有 SQLFactsExtractor 相同的
        physical table naming 语义。
        """

        parts = (
            table.catalog,
            table.db,
            table.name,
        )

        return ".".join(
            part.lower()
            for part
            in parts
            if part
        )

    @staticmethod
    def _select_aliases(
        expression: exp.Expression,
    ) -> set[str]:
        """
        只读取当前 Scope 根 SELECT 的投影 alias。

        不向下穿透其它 Scope。
        """

        if not isinstance(
            expression,
            exp.Select,
        ):
            return set()

        return {
            projection.alias.lower()
            for projection
            in expression.expressions
            if projection.alias
        }

    @staticmethod
    def _has_select_star(
        expression: exp.Expression,
    ) -> bool:
        """
        只判断当前 Scope 的 SELECT projection。

        COUNT(*) 不属于 SELECT *。
        """

        if not isinstance(
            expression,
            exp.Select,
        ):
            return False

        for projection in (
            expression.expressions
        ):
            if isinstance(
                projection,
                exp.Star,
            ):
                return True

            if (
                isinstance(
                    projection,
                    exp.Column,
                )
                and isinstance(
                    projection.this,
                    exp.Star,
                )
            ):
                return True

        return False