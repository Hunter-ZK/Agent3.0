from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.analysis.facts import (
    SQLFacts,
)
from sql_pilot_engine.program.enums import (
    ParameterUsageKind,
    ProgramAnalysisStatus,
    StatementKind,
    WriteStrategy,
)


@dataclass(
    frozen=True,
    slots=True,
)
class SourcePosition:
    """
    Raw SQL 中一个确定位置。

    line / column 使用 1-based，
    offset 使用 Python string 的 0-based offset。
    """

    offset: int
    line: int
    column: int


@dataclass(
    frozen=True,
    slots=True,
)
class SourceSpan:
    """
    Raw SQL 中一个半开区间：

        [start_offset, end_offset)

    也就是：

        raw_sql[
            start_offset:end_offset
        ]

    使用半开区间是为了与 Python slicing、
    Patch insertion/replacement 保持一致。
    """

    start: SourcePosition
    end: SourcePosition


@dataclass(
    frozen=True,
    slots=True,
)
class SourceMap:
    """
    Program Preprocessing 的位置映射。

    raw_text:
        用户原始 SQL。

    normalized_text:
        交给 SQLParser 的 SQL。

    normalized_to_raw:
        normalized 每个字符对应的 raw offset。

        CompatibilityPatch 新插入的字符没有直接 raw
        来源，因此值为 None。

    raw_to_normalized:
        raw 每个字符对应 normalized offset。

        被 Preprocessing 删除的 SET 等字符没有 normalized
        对应位置，因此值为 None。

    这就是 Phase 4.2 冻结设计中的：

        Raw SQL
            ↔
        Normalized SQL
    """

    raw_text: str
    normalized_text: str

    normalized_to_raw: tuple[
        int | None,
        ...,
    ]

    raw_to_normalized: tuple[
        int | None,
        ...,
    ]

    def normalized_offset_to_raw(
        self,
        offset: int,
        *,
        nearest: bool = True,
    ) -> int | None:
        """
        将 normalized offset 映射回 Raw SQL。

        CompatibilityPatch 插入的字符可能没有直接来源。

        nearest=True 时：
        向两侧寻找最近具有 Raw 来源的字符。

        Fix 2.0 最终做 Source Patch 时仍需要
        expected source 校验，不能只依赖 nearest。
        """

        if (
            offset < 0
            or offset
            >= len(
                self.normalized_to_raw
            )
        ):
            return None

        direct = (
            self.normalized_to_raw[
                offset
            ]
        )

        if (
            direct is not None
            or not nearest
        ):
            return direct

        distance = 1

        while (
            offset - distance >= 0
            or offset + distance
            < len(
                self.normalized_to_raw
            )
        ):
            left = offset - distance

            if left >= 0:
                candidate = (
                    self
                    .normalized_to_raw[
                        left
                    ]
                )

                if candidate is not None:
                    return candidate

            right = offset + distance

            if right < len(
                self.normalized_to_raw
            ):
                candidate = (
                    self
                    .normalized_to_raw[
                        right
                    ]
                )

                if candidate is not None:
                    return candidate

            distance += 1

        return None

    def raw_offset_to_normalized(
        self,
        offset: int,
    ) -> int | None:
        """
        将 Raw SQL offset 映射到 normalized SQL。

        被删除的 SET 内容没有对应 normalized offset，
        因此返回 None。
        """

        if (
            offset < 0
            or offset
            >= len(
                self.raw_to_normalized
            )
        ):
            return None

        return self.raw_to_normalized[
            offset
        ]

    def normalized_span_to_raw(
        self,
        start_offset: int,
        end_offset: int,
    ) -> SourceSpan | None:
        """
        将 normalized 半开区间映射回 Raw SQL。

        新插入的 CompatibilityPatch 字符会被忽略，
        只使用具有 Raw 来源的字符计算 envelope。
        """

        if (
            start_offset < 0
            or end_offset
            > len(
                self.normalized_text
            )
            or start_offset
            >= end_offset
        ):
            return None

        raw_offsets = tuple(
            raw_offset
            for raw_offset
            in self.normalized_to_raw[
                start_offset:
                end_offset
            ]
            if raw_offset is not None
        )

        if not raw_offsets:
            return None

        raw_start = min(
            raw_offsets
        )

        raw_end = (
            max(raw_offsets)
            + 1
        )

        return build_source_span(
            self.raw_text,
            raw_start,
            raw_end,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SessionHint:
    """
    从 Program Header 中抽取的 SET 指令。

    SET 不进入 SQLParser，
    但仍属于 SQL Program 的执行上下文事实。
    """

    name: str
    value: str
    raw_text: str
    span: SourceSpan


@dataclass(
    frozen=True,
    slots=True,
)
class ParameterBinding:
    """
    一个 Program 级调度参数。

    同一个变量只有一个 ParameterBinding，
    occurrences 保存它在 Raw SQL 中的全部位置。
    """

    name: str

    occurrences: tuple[
        SourceSpan,
        ...,
    ]

    usage_kinds: tuple[
        ParameterUsageKind,
        ...,
    ]

    inferred_format: (
        str | None
    ) = None


@dataclass(
    frozen=True,
    slots=True,
)
class AppliedCompatibilityPatch:
    """
    已应用的 dialect compatibility evidence。

    native_verified=False 表示：

        “这个变换帮助 SQLGlot/Spark 理解 SQL”

    不等于：

        “已经证明 ODPS 原生支持原始语法”。
    """

    patch_id: str

    native_verified: bool

    edit_count: int

    note: str = ""


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnSpec:
    """
    Program 输出字段的最小结构描述。

    Phase 4.2 只定义 Contract。
    output_schema 在 Phase 4.4 Schema Propagation 后填充。
    """

    name: str
    data_type: str = ""

    nullable: (
        bool | None
    ) = None


@dataclass(
    frozen=True,
    slots=True,
)
class PartitionBinding:
    """
    INSERT partition specification。

    value=None：

        PARTITION(batch_num)

    表示动态分区。

    value!=None：

        PARTITION(dt='202501')

    表示静态分区表达式。
    """

    name: str

    value: (
        str | None
    )

    is_dynamic: bool


@dataclass(
    frozen=True,
    slots=True,
)
class WriteTarget:
    """
    一个 SQL Statement 的确定性写入目标。
    """

    table_name: str

    strategy: WriteStrategy

    partition_spec: tuple[
        PartitionBinding,
        ...,
    ] = ()


@dataclass(
    frozen=True,
    slots=True,
)
class CTENode:
    """
    SQL Program 内一个 CTE 节点。

    dependencies 只记录 CTE → CTE 依赖，
    不把物理表混进 DAG。
    """

    name: str
    statement_index: int
    scope_id: str

    dependencies: tuple[
        str,
        ...,
    ] = ()


@dataclass(
    frozen=True,
    slots=True,
)
class ProgramScopeAnalysis:
    """
    Scoped SQLFacts wrapper。

    这是 v2.1 冻结的关键设计：

        SQLFacts
            不修改

        ProgramScopeAnalysis
            包装某一个 statement / CTE 的 SQLFacts

    Query Line 因此不需要 Contract Migration。
    """

    scope_id: str
    statement_index: int
    cte_name: str | None

    facts: SQLFacts

    output_schema: (
        tuple[
            ColumnSpec,
            ...,
        ]
        | None
    ) = None


@dataclass(
    frozen=True,
    slots=True,
)
class SQLStatement:
    """
    Program 中的一条 SQL statement。
    """

    index: int

    kind: StatementKind

    normalized_sql: str

    write_target: (
        WriteTarget | None
    ) = None

    cte_names: tuple[
        str,
        ...,
    ] = ()


@dataclass(
    frozen=True,
    slots=True,
)
class SQLProgram:
    """
    Complex SQL 的 Program Domain Model。

    注意：
    不保存 QueryPlan。
    Program Line 与 Query Line 物理分离。
    """

    raw_sql: str
    normalized_sql: str

    statements: tuple[
        SQLStatement,
        ...,
    ]

    cte_nodes: tuple[
        CTENode,
        ...,
    ]

    scope_analyses: tuple[
        ProgramScopeAnalysis,
        ...,
    ]

    session_hints: tuple[
        SessionHint,
        ...,
    ]

    parameters: tuple[
        ParameterBinding,
        ...,
    ]

    source_map: SourceMap

    applied_patches: tuple[
        AppliedCompatibilityPatch,
        ...,
    ] = ()


@dataclass(
    frozen=True,
    slots=True,
)
class ProgramAnalysisResult:
    """
    Program Analysis 对外唯一结果 Contract。

    成功但不完整时必须显式 PARTIAL，
    不允许返回“看起来正常”的空结构。
    """

    status: ProgramAnalysisStatus

    program: (
        SQLProgram | None
    )

    diagnostics: tuple[
        str,
        ...,
    ] = ()

    unsupported_features: tuple[
        str,
        ...,
    ] = ()

    failure_reason: (
        str | None
    ) = None


def build_source_position(
    text: str,
    offset: int,
) -> SourcePosition:
    """
    根据 Raw SQL offset 构造 1-based line/column。
    """

    safe_offset = max(
        0,
        min(
            offset,
            len(text),
        ),
    )

    line = (
        text.count(
            "\n",
            0,
            safe_offset,
        )
        + 1
    )

    last_newline = text.rfind(
        "\n",
        0,
        safe_offset,
    )

    if last_newline < 0:
        column = safe_offset + 1
    else:
        column = (
            safe_offset
            - last_newline
        )

    return SourcePosition(
        offset=safe_offset,
        line=line,
        column=column,
    )


def build_source_span(
    text: str,
    start_offset: int,
    end_offset: int,
) -> SourceSpan:
    """
    根据 Raw SQL 的半开 offset 区间构造 SourceSpan。
    """

    return SourceSpan(
        start=build_source_position(
            text,
            start_offset,
        ),
        end=build_source_position(
            text,
            end_offset,
        ),
    )