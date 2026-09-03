from __future__ import annotations

import re

from dataclasses import dataclass

from sql_pilot_engine.program.models import (
    ParameterOccurrence,
    ProgramPreprocessResult,
    SessionHint,
    SourceMap,
    build_source_span,
)


# ============================================================
# 【架构位置】
#
# Raw Production SQL
#         ↓
# preprocess_program_sql()
#         ↓
# Normalized SQL
#         ↓
# Existing SQLParser
#         ↓
# SQLGlot AST
#
#
# 本模块只负责：
#
# 1. 从生产脚本中分离 SET；
# 2. 识别 ${parameter}；
# 3. 将参数换成 Parser-safe token；
# 4. 维护 Normalized SQL → Raw SQL 的位置映射。
#
#
# 本模块明确不负责：
#
# - SQL 是否正确；
# - 表和字段是否合法；
# - 参数是什么业务含义；
# - CTE 之间怎么依赖；
# - SQL lineage；
# - SQL validation；
# - SQL fix。
#
# 这些属于后续 Program Analysis。
# ============================================================


_PARAMETER_PATTERN = re.compile(
    r"\$\{"
    r"(?P<name>"
    r"[A-Za-z_]"
    r"[A-Za-z0-9_]*"
    r")"
    r"\}"
)

# 上面的正则匹配：
#
#     ${biz_date}
#     ${month}
#     ${run_period_01}
#
# 但不会匹配非常任意的模板表达式。
#
# 当前支持的 Parameter Contract 明确限制为：
#
#     ${identifier}
#
# identifier 规则：
#
#     第一个字符：
#         字母或 _
#
#     后续字符：
#         字母 / 数字 / _
#
#
# 为什么当前不支持：
#
#     ${date-1}
#     ${foo.bar}
#     ${func(x)}
#
# 因为这些已经不仅是“参数名称”，
# 而可能是模板语言表达式。
#
# 如果以后真实生产 SQL 出现，
# 应该显式扩展 Template Syntax，
# 而不是让当前正则随意猜测。


@dataclass
class _MappedText:
    """
    Preprocessor 内部使用的临时结构。

    【为什么这个类不放 models.py】

    因为它不是 Program Domain Contract。

    外部模块：

        Explain
        Fix
        Evaluation

    都不应该知道它的存在。

    它只是 preprocessing.py 内部方便维护字符串
    和 SourceMap 的实现工具。


    【text】

    当前已经处理到哪一步的 SQL。


    【raw_offsets】

    raw_offsets[i] 表示：

        text[i]

    当前这个字符来自 Raw SQL 的哪个 offset。


    初始状态：

        text == raw_sql

        raw_offsets == [
            0,
            1,
            2,
            3,
            ...
        ]


    删除 SET 后：

        对应字符和 offset 一起删除。


    替换 ${parameter} 后：

        analyzer token 的字符映射回
        原始 ${parameter} 范围。
    """

    text: str

    raw_offsets: list[
        int | None
    ]

    @classmethod
    def from_raw(
        cls,
        raw_sql: str,
    ) -> "_MappedText":
        """
        从完全未经修改的 Raw SQL 创建初始映射。

        【range(len(raw_sql))】

        例如：

            Raw SQL = "ABC"

        那么：

            raw_offsets = [0, 1, 2]

        表示：

            当前 A → Raw A
            当前 B → Raw B
            当前 C → Raw C
        """

        return cls(
            text=raw_sql,
            raw_offsets=list(
                range(
                    len(raw_sql)
                )
            ),
        )

    def delete(
        self,
        *,
        start: int,
        end: int,
    ) -> None:
        """
        从 Normalized representation 中删除一段文本。

        【典型场景】

            SET x=1;

        不需要进入 SQLParser，

        因此从当前 Analyzer SQL 中删除。


        【为什么同时删除 raw_offsets】

        text 和 raw_offsets 必须始终一一对应：

            len(text)
            ==
            len(raw_offsets)

        如果只删 SQL 文本、不删位置映射，
        后面所有 SourceMap 都会整体错位。
        """

        if not (
            0
            <= start
            <= end
            <= len(self.text)
        ):
            raise ValueError(
                "Invalid deletion range."
            )

        self.text = (
            self.text[:start]
            + self.text[end:]
        )

        del self.raw_offsets[
            start:end
        ]

    def replace(
        self,
        *,
        start: int,
        end: int,
        replacement: str,
    ) -> None:
        """
        将当前 SQL 的一段文本替换成 Analyzer token。

        【本轮唯一实际用途】

            ${biz_date}

        替换为：

            __sqlpilot_parameter_000001__


        【重点】

        我们不是把参数“求值”。

        绝对不是：

            ${biz_date}
                ↓
            20260903

        因为 Agent 当前根本不知道真实运行值。


        我们只是把模板语法换成：

            SQLGlot 更容易稳定识别的内部 token。


        【位置映射怎么处理】

        replacement 往往比原 placeholder 更长。

        例如：

            Raw:
                ${x}

            Analyzer:
                __sqlpilot_parameter_000001__


        我们需要让这个 Analyzer token
        仍然能整体映射回 `${x}`。

        所以通过 _build_replacement_mapping()
        把 Analyzer token 中的字符分布映射到
        原始 `${x}` 的完整范围。
        """

        if not (
            0
            <= start
            < end
            <= len(self.text)
        ):
            raise ValueError(
                "Invalid replacement range."
            )

        original_offsets = (
            self.raw_offsets[
                start:end
            ]
        )

        usable_offsets = [
            offset
            for offset
            in original_offsets
            if offset is not None
        ]

        if not usable_offsets:
            raise ValueError(
                "Replacement has no "
                "raw source mapping."
            )

        raw_start = min(
            usable_offsets
        )

        raw_end = (
            max(
                usable_offsets
            )
            + 1
        )

        replacement_mapping = (
            _build_replacement_mapping(
                raw_start=raw_start,
                raw_end=raw_end,
                replacement_length=len(
                    replacement
                ),
            )
        )

        self.text = (
            self.text[:start]
            + replacement
            + self.text[end:]
        )

        self.raw_offsets[
            start:end
        ] = replacement_mapping

    def trim(
        self,
    ) -> None:
        """
        同步执行 SQLParser 所需要的 strip()。

        【为什么这里也必须 trim】

        现有 SQLParser 会：

            sql.strip()

        如果 ProgramPreprocessor 不提前同步处理，

        SourceMap 认为：

            normalized offset = 10

        SQLParser strip 后实际却变成：

            AST offset = 6

        两边坐标系就不一致。


        因此：

            text
            raw_offsets

        必须一起 trim。
        """

        start = 0

        end = len(
            self.text
        )

        while (
            start < end
            and self.text[
                start
            ].isspace()
        ):
            start += 1

        while (
            end > start
            and self.text[
                end - 1
            ].isspace()
        ):
            end -= 1

        self.text = (
            self.text[
                start:end
            ]
        )

        self.raw_offsets = (
            self.raw_offsets[
                start:end
            ]
        )

    def raw_range(
        self,
        *,
        start: int,
        end: int,
    ) -> tuple[
        int,
        int,
    ]:
        """
        返回当前 text 区间在 Raw SQL 中对应的范围。

        当前阶段主要用于：

            SET
            Parameter

        定位原始位置。
        """

        offsets = [
            offset
            for offset
            in self.raw_offsets[
                start:end
            ]
            if offset is not None
        ]

        if not offsets:
            raise ValueError(
                "Mapped range has no "
                "raw offsets."
            )

        return (
            min(offsets),
            max(offsets) + 1,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class _PendingParameter:
    """
    参数处理过程中的内部临时结果。

    【为什么需要 Pending】

    参数替换发生时：

        ${biz_date}
            ↓
        __sqlpilot_parameter_000001__

    后面 SET 删除、trim 等操作仍可能改变
    Analyzer SQL 的整体 offset。

    因此我们先保存：

        name
        Raw SQL 位置
        analyzer_token

    等所有 preprocessing 完成后，

    再在最终 normalized_sql 中确认 token 的最终位置。

    这样 ParameterOccurrence.normalized_span
    永远使用最终 Analyzer 坐标。
    """

    name: str

    raw_start: int

    raw_end: int

    analyzer_token: str


def preprocess_program_sql(
    raw_sql: str,
) -> ProgramPreprocessResult:
    """
    对生产 SQL 执行 Phase 4.2-A1 输入预处理。

    ========================================================
    【输入】
    ========================================================

    raw_sql:
        用户提供的原始生产 SQL。

        这里必须是：

            未经 Agent 修改的 SQL。

        因为 SourceMap 最终需要回到这份源码。


    ========================================================
    【处理顺序】
    ========================================================

    Raw SQL
        ↓
    1. 创建 Raw → Current 一一对应映射
        ↓
    2. 提取 top-level SET
        ↓
    3. 识别并 shielding ${parameter}
        ↓
    4. trim
        ↓
    Normalized SQL


    ========================================================
    【为什么 SET 要先处理】
    ========================================================

    SET 属于运行环境，不属于当前业务 SQL AST。

    如果 SET 中也出现模板内容，

    当前 A1 阶段把它保存在：

        SessionHint.raw_text

    而不将其作为 SQL 主体 ParameterOccurrence。

    SQL 主体参数与 Session 参数暂时明确分层。


    ========================================================
    【返回】
    ========================================================

    ProgramPreprocessResult：

        raw_sql
        normalized_sql
        source_map
        session_hints
        parameters


    ========================================================
    【注意】
    ========================================================

    normalized_sql 只是：

        Analyzer Representation

    绝不能：

        write_text(normalized_sql)

    去覆盖用户原始 SQL。
    """

    if not raw_sql.strip():
        raise ValueError(
            "Program SQL cannot be empty."
        )

    # --------------------------------------------------------
    # 从 Raw SQL 建立最初的一一映射。
    #
    # 此刻：
    #
    #     mapped.text == raw_sql
    #
    # 每个字符都能直接回到自己的 Raw offset。
    # --------------------------------------------------------

    mapped = (
        _MappedText.from_raw(
            raw_sql
        )
    )

    # --------------------------------------------------------
    # 第一步：
    #
    # 把 top-level SET 从业务 SQL 主体中分离出去。
    #
    # session_hints 中仍保存完整信息，
    # 所以不是“丢掉 SET”。
    # --------------------------------------------------------

    session_hints = (
        _extract_session_hints(
            raw_sql=raw_sql,
            mapped=mapped,
        )
    )

    # --------------------------------------------------------
    # 第二步：
    #
    # 查找业务 SQL 主体中的：
    #
    #     ${parameter}
    #
    # 并换成唯一 Analyzer token。
    #
    # 参数没有被赋真实值，
    # 这里只做 Parser shielding。
    # --------------------------------------------------------

    pending_parameters = (
        _shield_parameters(
            mapped=mapped
        )
    )

    # --------------------------------------------------------
    # 第三步：
    #
    # 与现有 SQLParser 的 sql.strip() 保持一致。
    #
    # 关键不是为了“代码好看”，
    # 而是为了保证 AST offset 与 SourceMap offset
    # 使用完全一致的坐标系。
    # --------------------------------------------------------

    mapped.trim()

    # --------------------------------------------------------
    # normalized SQL 已经确定。
    #
    # 此时可以正式构造 SourceMap。
    # --------------------------------------------------------

    source_map = SourceMap(
        raw_text=raw_sql,
        normalized_text=mapped.text,
        normalized_to_raw=tuple(
            mapped.raw_offsets
        ),
    )

    # --------------------------------------------------------
    # Parameter 的 normalized span 必须等最终 SQL
    # 确定后才能计算。
    # --------------------------------------------------------

    parameters = (
        _finalize_parameters(
            raw_sql=raw_sql,
            normalized_sql=(
                mapped.text
            ),
            pending_parameters=(
                pending_parameters
            ),
        )
    )

    return ProgramPreprocessResult(
        raw_sql=raw_sql,
        normalized_sql=mapped.text,
        source_map=source_map,
        session_hints=session_hints,
        parameters=parameters,
    )


def _extract_session_hints(
    *,
    raw_sql: str,
    mapped: _MappedText,
) -> tuple[
    SessionHint,
    ...,
]:
    """
    从 SQL Program 中抽取 top-level SET statements。

    ========================================================
    【为什么不能简单 regex：^SET.*】
    ========================================================

    因为下面 SQL：

        SELECT 'SET x=1;' AS text;

    字符串里面虽然出现 SET 和分号，

    但它根本不是一个 SET Statement。


    还可能出现：

        -- SET x=1;

        /* SET x=1; */

    都不能误判。


    所以这里先用：

        _find_statement_ranges()

    找出真正不在：

        quote
        line comment
        block comment

    中的 statement boundary。


    ========================================================
    【处理结果】
    ========================================================

    SET：

        保存为 SessionHint
        从 Normalized SQL 删除

    普通 SELECT / INSERT：

        保持不动
    """

    statement_ranges = (
        _find_statement_ranges(
            mapped.text
        )
    )

    session_hints: list[
        SessionHint
    ] = []

    delete_ranges: list[
        tuple[int, int]
    ] = []

    for (
        statement_start,
        statement_end,
    ) in statement_ranges:

        # ----------------------------------------------------
        # 一个 statement 前面可能有：
        #
        # 空行
        # 空格
        # 注释
        #
        # 所以不能直接检查：
        #
        #     sql[statement_start:].startswith("SET")
        #
        # 先跳过无意义前缀。
        # ----------------------------------------------------

        content_start = (
            _skip_ignorable_prefix(
                sql=mapped.text,
                start=statement_start,
                end=statement_end,
            )
        )

        if content_start >= (
            statement_end
        ):
            continue

        # ----------------------------------------------------
        # 这里只判断：
        #
        #     Statement 第一个真正 keyword 是不是 SET
        #
        # 不判断 SQL 中任意位置有没有 "set" 字符串。
        # ----------------------------------------------------

        if not _starts_with_keyword(
            sql=mapped.text,
            start=content_start,
            end=statement_end,
            keyword="set",
        ):
            continue

        raw_start, raw_end = (
            mapped.raw_range(
                start=content_start,
                end=statement_end,
            )
        )

        raw_statement = raw_sql[
            raw_start:
            raw_end
        ]

        (
            name,
            value,
        ) = _parse_set_statement(
            raw_statement
        )

        session_hints.append(
            SessionHint(
                name=name,
                value=value,
                raw_text=(
                    raw_statement
                ),
                span=(
                    build_source_span(
                        text=raw_sql,
                        start=raw_start,
                        end=raw_end,
                    )
                ),
            )
        )

        delete_ranges.append(
            (
                content_start,
                statement_end,
            )
        )

    # --------------------------------------------------------
    # 为什么必须 reversed()？
    #
    # 假设：
    #
    #     SET A
    #     SET B
    #     SELECT
    #
    # 如果先删除前面的 SET A：
    #
    # 后面 SET B 的 offset 会整体向前移动。
    #
    # 原先计算好的位置立刻失效。
    #
    # 从后往前删除：
    #
    #     先删 B
    #     再删 A
    #
    # 前面的 offset 不受后面删除影响。
    #
    # 这是文本 Patch 中很常见的处理方式。
    # --------------------------------------------------------

    for (
        start,
        end,
    ) in reversed(
        delete_ranges
    ):
        mapped.delete(
            start=start,
            end=end,
        )

    return tuple(
        session_hints
    )


def _shield_parameters(
    *,
    mapped: _MappedText,
) -> tuple[
    _PendingParameter,
    ...,
]:
    """
    查找 `${name}`，并替换成唯一 Analyzer token。

    ========================================================
    【为什么使用 finditer() 而不是 findall()】
    ========================================================

    findall() 更适合：

        “我要匹配到了什么文本？”

    但这里还必须知道：

        参数从哪里开始？
        到哪里结束？

    finditer() 返回 Match Object，

    可以使用：

        match.start()
        match.end()
        match.group()

    因此非常适合 SourceMap。


    ========================================================
    【为什么每次 occurrence 使用不同 token】
    ========================================================

    SQL：

        WHERE a='${month}'
          AND b='${month}'

    如果两个都替换成：

        __parameter_month__

    后面再找 normalized offset 时，
    无法区分第一次和第二次 occurrence。


    因此使用：

        __sqlpilot_parameter_000001__
        __sqlpilot_parameter_000002__


    名字虽然相同，

    occurrence identity 不同。
    """

    matches = list(
        _PARAMETER_PATTERN.finditer(
            mapped.text
        )
    )

    pending_parameters: list[
        _PendingParameter
    ] = []

    replacements: list[
        tuple[
            int,
            int,
            str,
        ]
    ] = []

    token_number = 1

    for match in matches:

        # ----------------------------------------------------
        # 构造一个内部唯一 token。
        #
        # :06d 表示：
        #
        #     1 → 000001
        #     12 → 000012
        #
        # 这里只是为了 token 长度和日志更加稳定，
        # 没有业务含义。
        # ----------------------------------------------------

        token = (
            "__sqlpilot_parameter_"
            f"{token_number:06d}__"
        )

        # ----------------------------------------------------
        # 极低概率情况下，
        # 用户原 SQL 可能本来就有完全相同字段名。
        #
        # 为避免碰撞，继续递增编号。
        # ----------------------------------------------------

        while token in mapped.text:

            token_number += 1

            token = (
                "__sqlpilot_parameter_"
                f"{token_number:06d}__"
            )

        token_number += 1

        raw_start, raw_end = (
            mapped.raw_range(
                start=match.start(),
                end=match.end(),
            )
        )

        pending_parameters.append(
            _PendingParameter(
                name=match.group(
                    "name"
                ),
                raw_start=raw_start,
                raw_end=raw_end,
                analyzer_token=token,
            )
        )

        replacements.append(
            (
                match.start(),
                match.end(),
                token,
            )
        )

    # --------------------------------------------------------
    # 和删除 SET 一样：
    #
    # replacement 也必须从后往前执行。
    #
    # 因为 replacement 前后文本长度通常不同。
    #
    # 从后往前修改不会影响前面尚未执行的 offset。
    # --------------------------------------------------------

    for (
        start,
        end,
        token,
    ) in reversed(
        replacements
    ):
        mapped.replace(
            start=start,
            end=end,
            replacement=token,
        )

    return tuple(
        pending_parameters
    )


def _finalize_parameters(
    *,
    raw_sql: str,
    normalized_sql: str,
    pending_parameters: tuple[
        _PendingParameter,
        ...,
    ],
) -> tuple[
    ParameterOccurrence,
    ...,
]:
    """
    将内部 _PendingParameter 转为正式 ParameterOccurrence。

    【为什么现在才做】

    参数替换后：

        trim

    仍然可能改变 normalized offset。

    所以必须等 normalized_sql 完全确定之后，
    再计算 normalized_span。
    """

    occurrences: list[
        ParameterOccurrence
    ] = []

    for parameter in (
        pending_parameters
    ):

        # ----------------------------------------------------
        # analyzer_token 是全局唯一的，
        #
        # 因此 str.find() 可以准确定位当前 occurrence。
        # ----------------------------------------------------

        normalized_start = (
            normalized_sql.find(
                parameter.analyzer_token
            )
        )

        if normalized_start < 0:
            # ------------------------------------------------
            # 如果发生这种情况，
            # 代表 Preprocessor 自己把已经生成的 token
            # 弄丢了。
            #
            # 这是程序内部 Contract 被破坏，
            # 而不是用户 SQL 普通分析失败。
            #
            # 因此这里应该抛 RuntimeError，
            # 不能静默忽略。
            # ------------------------------------------------

            raise RuntimeError(
                "Parameter analyzer token "
                "was lost during preprocessing: "
                f"{parameter.analyzer_token}"
            )

        normalized_end = (
            normalized_start
            + len(
                parameter.analyzer_token
            )
        )

        occurrences.append(
            ParameterOccurrence(
                name=parameter.name,
                raw_span=(
                    build_source_span(
                        text=raw_sql,
                        start=(
                            parameter
                            .raw_start
                        ),
                        end=(
                            parameter
                            .raw_end
                        ),
                    )
                ),
                normalized_span=(
                    build_source_span(
                        text=normalized_sql,
                        start=(
                            normalized_start
                        ),
                        end=(
                            normalized_end
                        ),
                    )
                ),
                analyzer_token=(
                    parameter
                    .analyzer_token
                ),
            )
        )

    return tuple(
        occurrences
    )


def _build_replacement_mapping(
    *,
    raw_start: int,
    raw_end: int,
    replacement_length: int,
) -> list[
    int | None
]:
    """
    为 Analyzer replacement 建立最简单的 Raw offset 映射。

    ========================================================
    【问题是什么】
    ========================================================

    Raw：

        ${x}

    长度可能只有 4。

    Analyzer：

        __sqlpilot_parameter_000001__

    长度明显更长。


    如果所有 Analyzer token 字符都只映射：

        raw_start

    那么以后把整个 Analyzer token 映射回 Raw，
    只能得到：

        "$"

    而不是完整：

        "${x}"


    ========================================================
    【当前解决办法】
    ========================================================

    把 replacement 的字符均匀分布到：

        raw_start ... raw_end - 1

    并且保证：

        replacement 第一个字符
            → raw_start

        replacement 最后一个字符
            → raw_end - 1


    所以整个 normalized span 做：

        min(offset)
        max(offset)

    就能恢复完整 Raw placeholder。


    ========================================================
    【这是最终 Fix 2.0 算法吗】
    ========================================================

    不是。

    这是 Phase 4.2-A1 的简单 SourceMap 实现。

    Future Fix 2.0 会有更严格的：

        AST position
        SourceSpan
        expected source
        Source Patch

    当前不提前实现。
    """

    if replacement_length <= 0:
        return []

    raw_length = (
        raw_end
        - raw_start
    )

    if raw_length <= 0:
        return [
            None
        ] * replacement_length

    if replacement_length == 1:
        return [
            raw_start
        ]

    if raw_length == 1:
        return [
            raw_start
        ] * replacement_length

    mapping: list[
        int | None
    ] = []

    for index in range(
        replacement_length
    ):

        # ----------------------------------------------------
        # 将：
        #
        #     0 ... replacement_length - 1
        #
        # 按比例映射到：
        #
        #     0 ... raw_length - 1
        #
        # round() 保证两端都能覆盖。
        # ----------------------------------------------------

        raw_relative_offset = round(
            index
            * (
                raw_length
                - 1
            )
            / (
                replacement_length
                - 1
            )
        )

        mapping.append(
            raw_start
            + raw_relative_offset
        )

    return mapping


def _find_statement_ranges(
    sql: str,
) -> tuple[
    tuple[int, int],
    ...,
]:
    """
    找到 SQL Program 的 statement 边界。

    ========================================================
    【这个函数是不是在重写 SQL Parser？】
    ========================================================

    不是。

    它完全不理解：

        SELECT
        JOIN
        CTE
        WHERE
        INSERT

    它只做一个非常小的 lexical task：

        找到“不在字符串和注释中的分号”。


    ========================================================
    【为什么需要自己扫描】
    ========================================================

    我们现在就是在 SQLParser 之前处理 SET。

    所以不能先要求：

        SQLGlot 已经成功 parse

    然后再找 SET。

    否则产生循环依赖。


    ========================================================
    【必须处理哪些情况】
    ========================================================

    下面这些分号不能算 statement boundary：

        SELECT 'abc;def';

        -- fake ;

        /* fake ; */


    所以扫描器必须知道当前是否在：

        quote
        line comment
        block comment

    内。
    """

    ranges: list[
        tuple[int, int]
    ] = []

    statement_start = 0

    cursor = 0

    quote: str | None = None

    while cursor < len(sql):

        char = sql[
            cursor
        ]

        # ----------------------------------------------------
        # 当前位于 quoted content 中。
        # ----------------------------------------------------

        if quote is not None:

            # ------------------------------------------------
            # 对反斜杠 escape 做保守跳过：
            #
            #     'abc\\'def'
            #
            # 不让 escaped quote 误结束字符串。
            # ------------------------------------------------

            if (
                char == "\\"
                and cursor + 1
                < len(sql)
            ):
                cursor += 2
                continue

            if char == quote:

                # ------------------------------------------------
                # SQL 常见 doubled quote：
                #
                #     'it''s'
                #
                # 中间两个单引号表示字符串中的一个引号，
                # 不是 string termination。
                # ------------------------------------------------

                if (
                    cursor + 1
                    < len(sql)
                    and sql[
                        cursor + 1
                    ]
                    == quote
                ):
                    cursor += 2
                    continue

                quote = None

            cursor += 1
            continue

        # ----------------------------------------------------
        # 进入 quoted content。
        #
        # 当前识别：
        #
        #     'string'
        #     "identifier/string"
        #     `identifier`
        # ----------------------------------------------------

        if char in {
            "'",
            '"',
            "`",
        }:
            quote = char
            cursor += 1
            continue

        # ----------------------------------------------------
        # -- line comment
        #
        # 直接跳到下一行。
        # ----------------------------------------------------

        if sql.startswith(
            "--",
            cursor,
        ):
            newline = sql.find(
                "\n",
                cursor + 2,
            )

            if newline < 0:
                # 文件已经结束。
                cursor = len(sql)
                break

            cursor = (
                newline
                + 1
            )

            continue

        # ----------------------------------------------------
        # /* block comment */
        #
        # 直接跳过整个 comment。
        # ----------------------------------------------------

        if sql.startswith(
            "/*",
            cursor,
        ):
            comment_end = (
                sql.find(
                    "*/",
                    cursor + 2,
                )
            )

            if comment_end < 0:
                # 当前只是 Preprocessing lexical scanner。
                #
                # 未闭合 comment 最终会由真正 Parser /
                # Program Analysis 报错。
                #
                # 这里停止继续寻找 statement boundary。
                cursor = len(sql)
                break

            cursor = (
                comment_end
                + 2
            )

            continue

        # ----------------------------------------------------
        # 当前分号既不在 quote，
        # 也不在 comment。
        #
        # 因此可以作为一个真实 statement boundary。
        # ----------------------------------------------------

        if char == ";":

            ranges.append(
                (
                    statement_start,
                    cursor + 1,
                )
            )

            statement_start = (
                cursor + 1
            )

        cursor += 1

    # --------------------------------------------------------
    # 最后一条 SQL 可能没有 ";"。
    #
    # 例如：
    #
    #     SELECT * FROM t
    #
    # 仍然必须作为一个 statement range 保存。
    # --------------------------------------------------------

    if (
        statement_start
        < len(sql)
    ):
        ranges.append(
            (
                statement_start,
                len(sql),
            )
        )

    return tuple(
        ranges
    )


def _skip_ignorable_prefix(
    *,
    sql: str,
    start: int,
    end: int,
) -> int:
    """
    跳过一个 Statement 前面的：

        whitespace
        -- line comment
        /* block comment */

    【为什么存在】

    SQL 可能是：

        -- runtime config
        SET x=1;

    真正第一个 keyword 仍然是：

        SET

    不能因为前面有 comment 就识别失败。
    """

    cursor = start

    while cursor < end:

        if sql[
            cursor
        ].isspace():
            cursor += 1
            continue

        if sql.startswith(
            "--",
            cursor,
        ):
            newline = sql.find(
                "\n",
                cursor + 2,
                end,
            )

            if newline < 0:
                return end

            cursor = (
                newline
                + 1
            )

            continue

        if sql.startswith(
            "/*",
            cursor,
        ):
            comment_end = (
                sql.find(
                    "*/",
                    cursor + 2,
                    end,
                )
            )

            if comment_end < 0:
                return end

            cursor = (
                comment_end
                + 2
            )

            continue

        break

    return cursor


def _starts_with_keyword(
    *,
    sql: str,
    start: int,
    end: int,
    keyword: str,
) -> bool:
    """
    判断当前位置是否真正以 SQL keyword 开始。

    【为什么不能只用 startswith("set")】

    因为：

        setting_table

    也以：

        set

    开头。

    所以必须检查 keyword 后面是不是：

        identifier character

    如果是：

        字母
        数字
        _

    就说明并不是独立 SET keyword。
    """

    keyword_end = (
        start
        + len(keyword)
    )

    if keyword_end > end:
        return False

    if (
        sql[
            start:
            keyword_end
        ].lower()
        != keyword.lower()
    ):
        return False

    if keyword_end >= end:
        return True

    next_char = sql[
        keyword_end
    ]

    if (
        next_char.isalnum()
        or next_char == "_"
    ):
        return False

    return True


def _parse_set_statement(
    raw_statement: str,
) -> tuple[
    str,
    str | None,
]:
    """
    将：

        SET key=value;

    拆成：

        key
        value


    【为什么只 split 第一个 "="】

    value 本身可能继续包含 "="。

    例如某些配置值：

        SET option=a=b;

    如果直接：

        split("=")

    会得到三个部分。

    所以：

        split("=", 1)

    只拆第一次出现的 "="。


    【为什么不解释 value】

    Preprocessing 只保存运行上下文事实。

    value 是：

        true
        100
        xxx
        ${parameter}

    当前都只是字符串。

    不在这里猜类型或语义。
    """

    content = (
        raw_statement.strip()
    )

    if content.endswith(
        ";"
    ):
        content = (
            content[:-1]
            .rstrip()
        )

    # 前面已经确认 statement keyword 是 SET。
    #
    # 这里删除开头三个字符：
    #
    #     "SET"
    #
    # 再 strip() 去掉后续空格。
    content = (
        content[
            len("set"):
        ]
        .strip()
    )

    if "=" not in content:
        return (
            content,
            None,
        )

    name, value = (
        content.split(
            "=",
            1,
        )
    )

    return (
        name.strip(),
        value.strip(),
    )