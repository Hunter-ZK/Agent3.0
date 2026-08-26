from __future__ import annotations

from dataclasses import dataclass

from collections.abc import Mapping

from sql_pilot_engine.metadata.models import (
    TableMetadata,
)


@dataclass(frozen=True)
class LinkedTable:
    """
    当前任务已经成功关联到的物理表。

    LinkedTable 不是第二份 Metadata Model。

    真正的物理事实仍然只存在于：
        TableMetadata
        ColumnMetadata

    LinkedTable 只是 Schema Linking Stage
    对当前任务的引用结果。
    """

    metadata: TableMetadata


@dataclass(frozen=True)
class LinkedSchema:
    """
    SchemaLinker 的正式输出契约。

    表示：

    QueryPlan 中的业务意图
        ↓
    当前能够可靠落地到哪些物理 Schema。

    tables:
        已成功关联的真实物理表。

    unresolved_terms:
        当前不能可靠映射到物理 Schema
        的 Planner 输出项。

    omitted_column_count:
        因 Context Budget 等原因主动省略的字段数。

        Phase 2.1 当前不做字段级裁剪，
        因此固定为 0。

    linking_confidence:
        当前 Linking 请求中，
        成功确定性解析的比例。

        它不是 LLM 主观概率。
    """

    tables: tuple[
        LinkedTable,
        ...
    ]

    unresolved_terms: tuple[
        str,
        ...
    ] = ()

    omitted_column_count: int = 0

    linking_confidence: float = 1.0

    def __post_init__(
        self,
    ) -> None:

        if self.omitted_column_count < 0:
            raise ValueError(
                "omitted_column_count "
                "cannot be negative."
            )

        if not (
            0.0
            <= self.linking_confidence
            <= 1.0
        ):
            raise ValueError(
                "linking_confidence "
                "must be between 0 and 1."
            )

        names = [
            item.metadata.full_name
            for item
            in self.tables
        ]

        if (
            len(names)
            != len(set(names))
        ):
            raise ValueError(
                "LinkedSchema cannot "
                "contain duplicate tables."
            )

    @property
    def resolved(
        self,
    ) -> bool:
        """
        当前 Linking 是否已经完全解析。

        unresolved_terms 非空时，
        后续不能直接进入 Generation。
        """

        return not self.unresolved_terms

    def get_table(
        self,
        table_name: str,
    ) -> LinkedTable | None:

        normalized = (
            table_name
            .strip()
            .lower()
        )

        for linked_table in self.tables:

            full_name = (
                linked_table
                .metadata
                .full_name
            )

            if (
                full_name
                == normalized
            ):
                return linked_table

            # 支持：
            #
            # ods_xxx
            #
            # 与：
            #
            # project.ods_xxx
            #
            # 之间的逻辑匹配。
            if (
                full_name
                .split(".")[-1]
                == normalized
                .split(".")[-1]
            ):
                return linked_table

        return None