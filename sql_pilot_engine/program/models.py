from __future__ import annotations

from dataclasses import dataclass


# ============================================================
# 【架构位置】
#
# Raw Production SQL
#         ↓
# ProgramPreprocessor
#         ↓
# ProgramPreprocessResult
#         ├── normalized_sql
#         ├── session_hints
#         ├── parameters
#         └── source_map
#                 ↓
#            Existing SQLParser
#                 ↓
#             SQLGlot AST
#
#
# 当前 models.py 只定义：
#
#     Phase 4.2-A1
#     “生产 SQL 输入保真层”
#
# 所需要的数据结构。
#
#
# 当前明确不在这里定义：
#
#     SQLProgram
#     CTENode
#     StatementKind
#     ProgramScopeAnalysis
#     ParameterUsageKind
#     WriteTarget
#
# 这些属于后续 Phase 4.2-B。
#
#
# 这样做的原因：
#
# A1 当前只解决：
#
#     “生产 SQL 如何安全进入 Parser”
#
# 不能为了以后可能需要的能力，
# 提前把 Program Domain 全部塞进当前文件。
# ============================================================


@dataclass(
    frozen=True,
    slots=True,
)
class SourceLocation:
    """
    SQL 文本中的一个确定位置。

    ========================================================
    【这个类解决什么问题】
    ========================================================

    程序处理 SQL 时最方便使用的是：

        offset

    例如：

        sql[100]
        sql[100:120]

    但用户查看 SQL 时使用的是：

        第几行
        第几列

    所以 SourceLocation 同时保存：

        offset
        line
        column


    ========================================================
    【坐标约定】
    ========================================================

    offset:

        0-based。

        SQL 第一个字符：

            offset = 0


    line:

        1-based。

        第一行：

            line = 1


    column:

        1-based。

        第一列：

            column = 1


    ========================================================
    【为什么 frozen=True】
    ========================================================

    SourceLocation 是已经确定的源码事实。

    一旦创建以后，
    后面的分析模块不应该修改它。


    ========================================================
    【为什么 slots=True】
    ========================================================

    slots=True 会限制实例只能拥有声明过的字段。

    当前主要作用是：

        DTO 结构更加明确；

    同时可以减少大量 SourceLocation 对象产生时的
    一部分内存开销。

    这里不是核心设计，
    但与项目现有只读 DTO 风格一致。
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
    SQL 源码中的一段连续区域。

    ========================================================
    【为什么不是只保存 SourceLocation】
    ========================================================

    后续我们真正定位的一般不是：

        “某一个字符”

    而是：

        ${biz_date}

        amount

        SUM(amount)

        某一个 AST expression


    所以必须有：

        start
        end


    ========================================================
    【为什么采用半开区间】
    ========================================================

    SourceSpan 使用：

        [start, end)

    与 Python slicing 完全一致。


    例如：

        raw_sql[
            span.start.offset:
            span.end.offset
        ]

    可以直接取回这一段源码。


    end 指向：

        “源码片段结束后的第一个位置”

    而不是最后一个字符。
    """

    start: SourceLocation

    end: SourceLocation


@dataclass(
    frozen=True,
    slots=True,
)
class SourceMap:
    """
    Normalized SQL → Raw SQL 的位置映射。

    ========================================================
    【为什么需要 SourceMap】
    ========================================================

    用户真正提供的是：

        Raw SQL

    SQLParser 实际接收的是：

        Normalized SQL


    例如 Raw SQL：

        SET x=1;

        SELECT *
        FROM table_a;


    ProgramPreprocessor 把 SET 分离以后：

        SELECT *
        FROM table_a;


    此时 Parser 看到的：

        normalized offset = 0

    实际对应 Raw SQL 中：

        SELECT 的位置


    如果没有 SourceMap，

    后面 SQLGlot 即使告诉我们：

        “Analyzer SQL 第 100 个字符有问题”

    我们也无法安全找到：

        用户原始 SQL 的哪个字符有问题。


    ========================================================
    【A1 当前采用什么实现】
    ========================================================

    当前只采用：

        normalized_to_raw:
            tuple[int | None, ...]

    不使用：

        SourceMapSegment
        SourceMappingKind


    这点非常重要。


    ========================================================
    【normalized_to_raw 怎么理解】
    ========================================================

    假设：

        normalized_to_raw[20] = 37

    表示：

        Normalized SQL 第 20 个字符

    来源于：

        Raw SQL 第 37 个字符。


    这是最直接、最容易验证正确性的实现。


    ========================================================
    【为什么允许 None】
    ========================================================

    当前 A1 主要是删除和替换，

    但以后 Dialect Compatibility 可能插入：

        Raw SQL 本来不存在的字符。

    比如分析版本增加一个逗号。

    那个字符没有真实 Raw offset，

    所以类型预留：

        int | None


    ========================================================
    【非常重要】
    ========================================================

    SourceMap 只是：

        Analyzer Source Position
                ↓
        Raw Source Position

    的基础设施。

    它：

        不判断 SQL 是否正确；
        不做 AST；
        不做 lineage；
        不做 Fix。
    """

    raw_text: str

    normalized_text: str

    normalized_to_raw: tuple[
        int | None,
        ...,
    ]

    def __post_init__(
        self,
    ) -> None:
        """
        创建 SourceMap 时校验最基本 Contract。

        ====================================================
        【为什么需要这个检查】
        ====================================================

        normalized_text 与 normalized_to_raw
        必须严格一一对应。

        即：

            normalized_text 第 i 个字符

        必须有：

            normalized_to_raw[i]


        如果两者长度不同，

        说明 Preprocessor 修改 SQL 时没有同步维护
        SourceMap。

        这是系统内部错误，

        不应该等到后面的 Fix / Explain
        才发现。
        """

        if (
            len(
                self.normalized_text
            )
            != len(
                self.normalized_to_raw
            )
        ):
            raise ValueError(
                "normalized_text and "
                "normalized_to_raw must "
                "have the same length."
            )

    def normalized_offset_to_raw(
        self,
        offset: int,
    ) -> int | None:
        """
        Normalized SQL offset → Raw SQL offset。

        ====================================================
        【示例】
        ====================================================

        normalized SQL：

            SELECT *

        假设 SELECT 在 Raw SQL 中原本从 offset=20 开始。

        那么：

            normalized_offset_to_raw(0)

        应得到：

            20


        ====================================================
        【为什么越界返回 None】
        ====================================================

        “无法映射”

        属于源码定位层可以表达的状态。

        没必要让：

            IndexError

        直接泄漏到上层 Agent。
        """

        if (
            offset < 0
            or offset
            >= len(
                self.normalized_to_raw
            )
        ):
            return None

        return self.normalized_to_raw[
            offset
        ]

    def raw_offset_to_normalized(
        self,
        offset: int,
    ) -> int | None:
        """
        Raw SQL offset → Normalized SQL offset。

        ====================================================
        【这个方法为什么存在】
        ====================================================

        有时候我们已经知道 Raw SQL 中某个位置，

        需要知道：

            这个字符经过 Preprocessing 后还存在吗？


        例如：

            SET x=1;

        已经从 Normalized SQL 中删除。


        那么：

            raw_offset_to_normalized(
                SET 的 offset
            )

        应返回：

            None


        ====================================================
        【当前实现为什么直接遍历】
        ====================================================

        normalized_to_raw 本身就是：

            normalized → raw

        所以反向查询需要寻找：

            哪一个 normalized offset
            对应当前 raw offset。


        当前 SQL 的字符规模下，
        这种 O(n) 查询足够。

        A1 当前目标是：

            简单
            正确
            容易理解

        暂时没有必要再维护第二套反向索引。


        ====================================================
        【重要：这里绝不能再访问 segment.kind】
        ====================================================

        当前 Contract 是：

            tuple[int | None]

        所以循环里的 raw_offset 是：

            int
            或 None

        不是 SourceMapSegment。
        """

        if (
            offset < 0
            or offset
            >= len(
                self.raw_text
            )
        ):
            return None

        for (
            normalized_offset,
            raw_offset,
        ) in enumerate(
            self.normalized_to_raw
        ):
            if raw_offset == offset:
                return (
                    normalized_offset
                )

        return None

    def normalized_span_to_raw(
        self,
        *,
        start: int,
        end: int,
    ) -> SourceSpan | None:
        """
        将 Normalized SQL 中的一段区域映射回 Raw SQL。

        ====================================================
        【典型场景】
        ====================================================

        Raw SQL：

            ${biz_date}

        Normalized SQL：

            __sqlpilot_parameter_000001__


        Parser / Program Analysis 后面看到的是：

            __sqlpilot_parameter_000001__

        但用户真正的 SQL 里是：

            ${biz_date}


        所以需要：

            Normalized Span
                  ↓
              SourceMap
                  ↓
              Raw Span


        ====================================================
        【具体算法】
        ====================================================

        例如 normalized 区间：

            [20:50]

        我们取得：

            normalized_to_raw[20:50]

        得到其中所有真实 Raw offset。


        然后：

            raw_start = min(...)
            raw_end   = max(...) + 1


        最终构造成：

            SourceSpan


        ====================================================
        【为什么这里不再访问 normalized_start】
        ====================================================

        因为当前 A1 已经撤销：

            SourceMapSegment

        normalized_to_raw 中的每一个元素就是：

            int | None

        不存在：

            item.normalized_start
            item.kind


        这正是你当前两个失败测试的根因。
        """

        if (
            start < 0
            or end
            > len(
                self.normalized_text
            )
            or start
            >= end
        ):
            return None

        raw_offsets = [
            raw_offset
            for raw_offset
            in self.normalized_to_raw[
                start:end
            ]
            if raw_offset is not None
        ]

        if not raw_offsets:
            return None

        raw_start = min(
            raw_offsets
        )

        raw_end = (
            max(
                raw_offsets
            )
            + 1
        )

        return build_source_span(
            text=self.raw_text,
            start=raw_start,
            end=raw_end,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SessionHint:
    """
    从 SQL Program 主体中分离出来的 SET 配置。

    【示例】

        SET engine.option=true;


    Preprocessor 会：

        从 normalized SQL 中删除它；

    但是：

        保存为 SessionHint。


    因此：

        “不交给业务 SQL Parser”

    不等于：

        “丢掉执行上下文”。
    """

    name: str

    value: str | None

    raw_text: str

    span: SourceSpan


@dataclass(
    frozen=True,
    slots=True,
)
class ParameterOccurrence:
    """
    `${parameter}` 的一次实际出现。

    ========================================================
    【为什么保存 occurrence】
    ========================================================

    SQL：

        WHERE dt='${month}'

        PARTITION(dt='${month}')


    虽然参数名称都是：

        month

    但它出现了两次。


    后续 AST Analysis 可能发现：

        第一次是读取条件；

        第二次是写分区。


    所以 A1 当前必须保留每一次 occurrence。


    ========================================================
    【当前明确不做】
    ========================================================

    A1 不判断：

        参数是什么日期格式；
        参数是不是分区；
        参数是不是业务周期；
        参数是不是月份。


    当前只保存：

        参数名
        Raw SQL 位置
        Normalized SQL 位置
        Analyzer token
    """

    name: str

    raw_span: SourceSpan

    normalized_span: SourceSpan

    analyzer_token: str


@dataclass(
    frozen=True,
    slots=True,
)
class ProgramPreprocessResult:
    """
    Phase 4.2-A1 的最终输出。

    【调用链】

        raw_sql
            ↓
        preprocess_program_sql()
            ↓
        ProgramPreprocessResult
            ↓
        SQLParser.parse(
            result.normalized_sql
        )


    【注意】

    normalized_sql：

        只是 Analyzer 内部版本。

    永远不能用来：

        覆盖用户原始 SQL 文件。
    """

    raw_sql: str

    normalized_sql: str

    source_map: SourceMap

    session_hints: tuple[
        SessionHint,
        ...,
    ]

    parameters: tuple[
        ParameterOccurrence,
        ...,
    ]


def build_source_location(
    *,
    text: str,
    offset: int,
) -> SourceLocation:
    """
    将字符串 offset 转换成：

        offset
        line
        column


    【safe_offset】

    调用：

        max(
            0,
            min(
                offset,
                len(text),
            ),
        )

    是为了确保位置始终处于：

        0 <= offset <= len(text)


    【line】

    统计当前位置之前有多少：

        "\\n"

    再加 1。


    【column】

    找到当前 offset 之前最后一个：

        "\\n"

    然后计算距离。


    这是一个通用源码位置工具，
    后续 AST Diagnostic / Fix 仍可复用。
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

    last_newline = (
        text.rfind(
            "\n",
            0,
            safe_offset,
        )
    )

    if last_newline < 0:
        column = (
            safe_offset
            + 1
        )

    else:
        # 例如：
        #
        # "\nA"
        #
        # A 的 offset=1，
        # last_newline=0。
        #
        # column:
        #
        #     1 - 0 = 1
        #
        # 正好表示第 1 列。
        column = (
            safe_offset
            - last_newline
        )

    return SourceLocation(
        offset=safe_offset,
        line=line,
        column=column,
    )


def build_source_span(
    *,
    text: str,
    start: int,
    end: int,
) -> SourceSpan:
    """
    根据：

        start
        end

    构造半开区间 SourceSpan。

    调用方后续可以直接：

        text[
            span.start.offset:
            span.end.offset
        ]

    取回原始源码。
    """

    return SourceSpan(
        start=(
            build_source_location(
                text=text,
                offset=start,
            )
        ),
        end=(
            build_source_location(
                text=text,
                offset=end,
            )
        ),
    )