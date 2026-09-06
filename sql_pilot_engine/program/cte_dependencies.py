from __future__ import annotations

import heapq

from dataclasses import replace

from sqlglot import exp
from sqlglot.optimizer.scope import (
    Scope,
    traverse_scope,
)

from sql_pilot_engine.analysis.sql_parser import (
    SQLParseResult,
)
from sql_pilot_engine.program.models import (
    CTENode,
    SQLProgram,
)
from sql_pilot_engine.program.scope_resolver import (
    build_cte_expression_node_map,
)


class CTEDependencyResolver:
    """
    构建 SQL Program 内部的 CTE Dependency DAG。

    【架构位置】

        SQLProgram
            +
        SQLGlot Scope
            ↓
    CTEDependencyResolver
            ↓
        CTENode
        dependency_scope_ids

    本模块只回答：

        哪个 CTE 依赖哪个 CTE？

    不处理：
    - 物理表 lineage；
    - 字段 lineage；
    - Metadata；
    - Review；
    - Fix；
    - Generate。
    """

    def resolve(
        self,
        *,
        program: SQLProgram,
        parse_result: SQLParseResult,
    ) -> SQLProgram:
        if not parse_result.success:
            raise ValueError(
                "CTEDependencyResolver cannot "
                "resolve a failed parse result."
            )

        if (
            len(program.statements)
            != len(parse_result.statements)
        ):
            raise ValueError(
                "SQLProgram statements and "
                "parsed statements are inconsistent."
            )

        updated_nodes: dict[
            str,
            CTENode,
        ] = {}

        for (
            statement_index,
            expression,
        ) in enumerate(
            parse_result.statements
        ):
            statement_nodes = tuple(
                node
                for node
                in program.cte_nodes
                if (
                    node.statement_index
                    == statement_index
                )
            )

            if not statement_nodes:
                continue

            dependency_map = (
                self._resolve_statement(
                    expression=expression,
                    cte_nodes=statement_nodes,
                )
            )

            for node in statement_nodes:
                updated_nodes[
                    node.scope_id
                ] = replace(
                    node,
                    dependency_scope_ids=(
                        dependency_map[
                            node.scope_id
                        ]
                    ),
                )

        return replace(
            program,
            cte_nodes=tuple(
                updated_nodes.get(
                    node.scope_id,
                    node,
                )
                for node
                in program.cte_nodes
            ),
        )

    @classmethod
    def _resolve_statement(
        cls,
        *,
        expression: exp.Expression,
        cte_nodes: tuple[
            CTENode,
            ...,
        ],
    ) -> dict[
        str,
        tuple[
            str,
            ...,
        ],
    ]:
        """
        计算一条 Statement 内所有 CTE 的直接依赖。

        注意：

            A → B
            B → C

        A 的 dependency 只保存 B，
        不自动展开成：

            A → B, C

        transitive dependency 后续可由图遍历得到，
        不应重复存储。
        """

        scopes = traverse_scope(
            expression
        )

        cte_node_map = (
            build_cte_expression_node_map(
                expression=expression,
                cte_nodes=cte_nodes,
            )
        )

        dependencies: dict[
            str,
            set[
                str
            ],
        ] = {
            node.scope_id: set()
            for node
            in cte_nodes
        }

        node_order = {
            node.scope_id: index
            for (
                index,
                node,
            )
            in enumerate(
                cte_nodes
            )
        }

        for scope in scopes:
            owner = (
                cls._nearest_cte_owner(
                    scope=scope,
                    cte_node_map=cte_node_map,
                )
            )

            # Root statement 等不属于任何 CTE，
            # 不产生 CTE node dependency。
            if owner is None:
                continue

            for (
                _,
                source,
            ) in (
                scope
                .selected_sources
                .values()
            ):
                # 物理表：
                #
                #     exp.Table
                #
                # 不进入 CTE dependency graph。
                if not isinstance(
                    source,
                    Scope,
                ):
                    continue

                dependency = (
                    cte_node_map.get(
                        id(
                            source.expression
                        )
                    )
                )

                # derived table / subquery 等也是 Scope，
                # 但不是 CTE node。
                if dependency is None:
                    continue

                dependencies[
                    owner.scope_id
                ].add(
                    dependency.scope_id
                )

        return {
            scope_id: tuple(
                sorted(
                    dependency_ids,
                    key=lambda item: (
                        node_order[item]
                    ),
                )
            )
            for (
                scope_id,
                dependency_ids,
            )
            in dependencies.items()
        }

    @staticmethod
    def _nearest_cte_owner(
        *,
        scope: Scope,
        cte_node_map: dict[
            int,
            CTENode,
        ],
    ) -> CTENode | None:
        """
        找到某个 Scope 所属的最近 CTE。

        这解决一种真实复杂结构：

            CTE A
              └── nested subquery
                    └── FROM CTE B

        nested subquery 自己不是 CTE，
        但它发生在 A 的计算内部。

        因此应该得到：

            A → B
        """

        current: Scope | None = (
            scope
        )

        while current is not None:
            node = (
                cte_node_map.get(
                    id(
                        current.expression
                    )
                )
            )

            if node is not None:
                return node

            current = current.parent

        return None

    @staticmethod
    def topological_order(
        *,
        program: SQLProgram,
        statement_index: int,
    ) -> tuple[
        str,
        ...,
    ]:
        """
        返回某条 Statement 内 CTE 的拓扑顺序。

        返回 scope_id，而不是 name。

        顺序保证：

            dependency
                一定出现在
            dependent
                之前。

        如果无法得到完整拓扑序，
        说明 dependency graph 存在 cycle。
        """

        nodes = tuple(
            node
            for node
            in program.cte_nodes
            if (
                node.statement_index
                == statement_index
            )
        )

        if not nodes:
            return ()

        node_by_id = {
            node.scope_id: node
            for node
            in nodes
        }

        original_order = {
            node.scope_id: index
            for (
                index,
                node,
            )
            in enumerate(
                nodes
            )
        }

        indegree = {
            node.scope_id: len(
                node.dependency_scope_ids
            )
            for node
            in nodes
        }

        dependents: dict[
            str,
            list[
                str
            ],
        ] = {
            node.scope_id: []
            for node
            in nodes
        }

        for node in nodes:
            for dependency_id in (
                node.dependency_scope_ids
            ):
                if (
                    dependency_id
                    not in node_by_id
                ):
                    raise ValueError(
                        "CTE dependency references "
                        "a node outside the current "
                        "statement."
                    )

                dependents[
                    dependency_id
                ].append(
                    node.scope_id
                )

        ready: list[
            tuple[
                int,
                str,
            ]
        ] = [
            (
                original_order[
                    node.scope_id
                ],
                node.scope_id,
            )
            for node
            in nodes
            if (
                indegree[
                    node.scope_id
                ]
                == 0
            )
        ]

        heapq.heapify(
            ready
        )

        ordered: list[
            str
        ] = []

        while ready:
            (
                _,
                scope_id,
            ) = heapq.heappop(
                ready
            )

            ordered.append(
                scope_id
            )

            for dependent_id in (
                dependents[
                    scope_id
                ]
            ):
                indegree[
                    dependent_id
                ] -= 1

                if (
                    indegree[
                        dependent_id
                    ]
                    == 0
                ):
                    heapq.heappush(
                        ready,
                        (
                            original_order[
                                dependent_id
                            ],
                            dependent_id,
                        ),
                    )

        if (
            len(ordered)
            != len(nodes)
        ):
            remaining = [
                node.name
                for node
                in nodes
                if (
                    node.scope_id
                    not in ordered
                )
            ]

            raise ValueError(
                "CTE dependency cycle detected "
                f"in statement {statement_index}: "
                + ", ".join(
                    remaining
                )
            )

        return tuple(
            ordered
        )