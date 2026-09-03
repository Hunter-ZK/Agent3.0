from __future__ import annotations

import re

from sql_pilot_engine.dialects.protocols import (
    CompatibilityEdit,
)


# ============================================================
# 【架构位置】
#
# ProgramPreprocessor
#         ↓
# MaxComputeCompatibilityAdapter   ← 当前模块
#         ↓
# CompatibilityEdit
#
#
# 当前模块只处理：
#
#     MaxCompute / DataWorks SQL
#     与我们当前 Analyzer（SQLGlot）之间
#     已经实际观察到的兼容差异。
#
#
# 这里明确禁止：
#
# - 业务表名判断；
# - CTE 名判断；
# - 报表类型判断；
# - 参数业务语义判断；
# - SQL correctness 判断。
#
#
# 所以这个模块不是：
#
#     “某份生产 SQL 的补丁文件”
#
# 而是：
#
#     “MaxCompute → Analyzer 的方言适配器”
# ============================================================


_VALUES_ROW_SEPARATOR_PATCH_ID = (
    "odps_values_row_separator"
)


# re.compile()：
#
# 先把正则表达式编译成 Pattern 对象。
#
# 后面可以多次调用：
#
#     _FROM_VALUES_PATTERN.finditer(sql)
#
# 不需要每次重新解析正则。
#
#
# \b：
#     单词边界。
#
# 避免误匹配：
#
#     someFROM VALUES
#
#
# \s+：
#     FROM 与 VALUES 中间允许一个或多个：
#
#         空格
#         TAB
#         换行
#
#
# re.IGNORECASE：
#
#     FROM VALUES
#     from values
#     From Values
#
# 都可以识别。
_FROM_VALUES_PATTERN = re.compile(
    r"\bFROM\s+VALUES\b",
    flags=re.IGNORECASE,
)


class MaxComputeCompatibilityAdapter:
    """
    MaxCompute Program SQL 的 Analyzer Compatibility Adapter。

    ========================================================
    【当前只解决一个真实已知问题】
    ========================================================

    我们观察到生产 SQL 存在：

        FROM VALUES
            (1, 'A')
            (2, 'B')

    SQLGlot Hive Parser 无法稳定解析。

    补成：

        FROM VALUES
            (1, 'A'),
            (2, 'B')

    后可以正常进入结构分析。


    ========================================================
    【为什么这里只做一个 Patch】
    ========================================================

    Compatibility Layer 很容易变成：

        “看到什么报错就加一个正则”

    最终形成补丁垃圾场。

    所以规则是：

        只有真实复现过的 Dialect Gap
        才允许进入这里。

    当前 Phase 4.2-A2 只有这一项。
    """

    def collect_edits(
        self,
        sql: str,
    ) -> tuple[
        CompatibilityEdit,
        ...,
    ]:
        """
        扫描 SQL，并返回当前需要执行的 CompatibilityEdit。

        ====================================================
        【具体执行逻辑】
        ====================================================

        例如：

            SELECT *
            FROM VALUES
                (1, 'A')
                (2, 'B')
            AS t(id, name);

        第一步：

            找到：

                FROM VALUES

        第二步：

            从 VALUES 后面开始读取第一组：

                (1, 'A')

        第三步：

            读取完第一组后，跳过换行和空格。

        第四步：

            发现下一个字符直接是：

                (

            说明出现：

                (...)
                (...)

            中间没有逗号。

        第五步：

            创建：

                CompatibilityEdit(
                    replacement=","
                )

        注意：

            当前函数只是返回 Edit。

            真正修改 SQL 的动作仍然由
            ProgramPreprocessor 完成。
        """

        edits: list[
            CompatibilityEdit
        ] = []

        # finditer() 会返回每一个：
        #
        #     FROM VALUES
        #
        # 的 Match Object。
        #
        # Match Object 可以提供：
        #
        #     match.start()
        #     match.end()
        #
        # 我们需要 match.end()，
        # 因为下一步要从 VALUES 后面继续扫描。
        for match in (
            _FROM_VALUES_PATTERN.finditer(
                sql
            )
        ):

            values_edits = (
                _collect_values_row_edits(
                    sql=sql,
                    start=match.end(),
                )
            )

            edits.extend(
                values_edits
            )

        # ----------------------------------------------------
        # 理论上同一个位置不应该产生重复 Patch。
        #
        # 这里做一次去重属于防御式处理。
        #
        # dict 的 key 使用：
        #
        #     start
        #     end
        #     replacement
        #     patch_id
        #
        # 如果四个完全相同，
        # 就认为它们是同一个 edit。
        # ----------------------------------------------------

        unique_edits = {
            (
                edit.start,
                edit.end,
                edit.replacement,
                edit.patch_id,
            ): edit
            for edit in edits
        }

        # ----------------------------------------------------
        # 最终按源码 offset 排序。
        #
        # ProgramPreprocessor 后面会检查：
        #
        #     edit 是否重叠
        #
        # 并从后往前真正修改文本。
        # ----------------------------------------------------

        return tuple(
            sorted(
                unique_edits.values(),
                key=lambda edit: (
                    edit.start,
                    edit.end,
                ),
            )
        )


def _collect_values_row_edits(
    *,
    sql: str,
    start: int,
) -> list[
    CompatibilityEdit
]:
    """
    扫描某个 FROM VALUES 后面的 row constructors。

    ========================================================
    【为什么不能直接 regex 替换 ")\\n("】
    ========================================================

    因为：

        )
        (

    在普通 SQL 中可能出现在很多合法场景。

    例如：

        SELECT
            (
                amount + 1
            )
        FROM ...

    如果全局替换：

        )(
        ↓
        ),(

    会误伤其它 SQL。


    ========================================================
    【所以这里怎么做】
    ========================================================

    必须先确认：

        当前确实位于 FROM VALUES 后面。

    然后只在这一小段语法区域中扫描：

        (...)
        (...)
        (...)

    这就是所谓：

        context-bounded compatibility patch

    而不是：

        global regex patch。
    """

    edits: list[
        CompatibilityEdit
    ] = []

    # --------------------------------------------------------
    # FROM VALUES 后面通常有换行或空格：
    #
    #     FROM VALUES
    #         (1, 'A')
    #
    # 所以先跳过：
    #
    #     whitespace
    #     comment
    #
    # 找到第一个真正有效字符。
    # --------------------------------------------------------

    cursor = _skip_ignorable(
        sql=sql,
        start=start,
    )

    # --------------------------------------------------------
    # VALUES 后面如果不是 "("，
    # 当前这个 Patch 就不适用。
    #
    # 不猜、不强行修。
    # --------------------------------------------------------

    if (
        cursor >= len(sql)
        or sql[cursor] != "("
    ):
        return edits

    # --------------------------------------------------------
    # 只要当前位置仍然是 "("，
    # 就尝试读取一整个 VALUES row。
    # --------------------------------------------------------

    while (
        cursor < len(sql)
        and sql[cursor] == "("
    ):

        # ----------------------------------------------------
        # 找到当前：
        #
        #     (...)
        #
        # 的完整结束位置。
        #
        # 注意里面可能还有：
        #
        #     CONCAT(...)
        #     CAST(...)
        #     'abc)'
        #
        # 所以不能简单 sql.find(")")。
        # ----------------------------------------------------

        row_end = (
            _scan_parenthesized(
                sql=sql,
                start=cursor,
            )
        )

        # 没找到匹配的 ")"。
        #
        # 当前 Adapter 不负责修语法错误，
        # 所以立即停止。
        if row_end is None:
            break

        # ----------------------------------------------------
        # row_end 指向：
        #
        #     当前 ")" 后面的第一个位置
        #
        # 例如：
        #
        #     (1, 'A')
        #             ↑
        #             row_end
        #
        # 下一步跳过换行、空格、comment，
        # 看下一个真正字符是什么。
        # ----------------------------------------------------

        next_token = (
            _skip_ignorable(
                sql=sql,
                start=row_end,
            )
        )

        if next_token >= len(sql):
            break

        next_char = sql[
            next_token
        ]

        # ----------------------------------------------------
        # 情况 1：
        #
        #     (1, 'A'),
        #     (2, 'B')
        #
        # 已经存在逗号。
        #
        # 不需要 Patch。
        #
        # 跳过逗号，
        # 继续定位下一组 row。
        # ----------------------------------------------------

        if next_char == ",":

            cursor = (
                _skip_ignorable(
                    sql=sql,
                    start=(
                        next_token
                        + 1
                    ),
                )
            )

            continue

        # ----------------------------------------------------
        # 情况 2：
        #
        #     (1, 'A')
        #     (2, 'B')
        #
        # 下一有效字符直接是 "("。
        #
        # 这就是当前观察到的 compatibility gap。
        #
        # 在 row_end 处：
        #
        #     start == end
        #
        # 表示插入逗号。
        # ----------------------------------------------------

        if next_char == "(":

            edits.append(
                CompatibilityEdit(
                    start=row_end,
                    end=row_end,
                    replacement=",",
                    patch_id=(
                        _VALUES_ROW_SEPARATOR_PATCH_ID
                    ),
                    native_verified=False,
                    description=(
                        "Insert analyzer-only comma "
                        "between adjacent FROM VALUES "
                        "row constructors."
                    ),
                )
            )

            # 下一轮从第二个 "(" 开始。
            cursor = next_token

            continue

        # ----------------------------------------------------
        # 情况 3：
        #
        # row 后面既不是：
        #
        #     ,
        #
        # 也不是：
        #
        #     (
        #
        # 例如：
        #
        #     AS t(...)
        #     ;
        #
        # 说明 VALUES rows 已经结束。
        # ----------------------------------------------------

        break

    return edits


def _skip_ignorable(
    *,
    sql: str,
    start: int,
) -> int:
    """
    跳过 whitespace 和 SQL comment。

    ========================================================
    【为什么单独做这个函数】
    ========================================================

    SQL 中两个逻辑 token 之间可能存在：

        空格
        TAB
        换行
        -- comment
        /* comment */

    例如：

        (1)
        -- second row
        (2)

    从语法结构看：

        第一组 row 后面
        仍然紧接第二组 row。

    所以需要跳过这些不影响结构的字符。


    ========================================================
    【返回什么】
    ========================================================

    返回：

        下一个真正需要分析的字符 offset。
    """

    cursor = start

    while cursor < len(sql):

        # Python str.isspace() 可以识别：
        #
        #     " "
        #     "\\t"
        #     "\\n"
        #     "\\r"
        #
        # 所以这里不需要分别判断。
        if sql[
            cursor
        ].isspace():

            cursor += 1

            continue

        # ----------------------------------------------------
        # SQL 单行注释：
        #
        #     -- comment
        #
        # 找到下一行 "\\n"，
        # 然后继续扫描。
        # ----------------------------------------------------

        if sql.startswith(
            "--",
            cursor,
        ):

            newline = sql.find(
                "\n",
                cursor + 2,
            )

            # 注释已经一直持续到文件末尾。
            if newline < 0:
                return len(sql)

            cursor = (
                newline
                + 1
            )

            continue

        # ----------------------------------------------------
        # SQL block comment：
        #
        #     /* comment */
        # ----------------------------------------------------

        if sql.startswith(
            "/*",
            cursor,
        ):

            comment_end = sql.find(
                "*/",
                cursor + 2,
            )

            # comment 没有正常闭合。
            #
            # Compatibility Adapter 不负责修复语法错误，
            # 所以直接停止扫描。
            if comment_end < 0:
                return len(sql)

            cursor = (
                comment_end
                + 2
            )

            continue

        # 既不是 whitespace，
        # 也不是 comment。
        #
        # 找到真正 token。
        break

    return cursor


def _scan_parenthesized(
    *,
    sql: str,
    start: int,
) -> int | None:
    """
    找到一整段 (...) 的结束位置。

    ========================================================
    【为什么这个函数比 sql.find(")") 复杂】
    ========================================================

    例如：

        (
            1,
            CONCAT('A', ')')
        )

    第一个 ")" 并不是真正 row 的结束。

    又例如：

        (
            CAST(amount AS DECIMAL(18, 2))
        )

    中间还有嵌套括号。

    所以必须维护：

        depth

    表示当前进入了几层括号。


    ========================================================
    【核心算法】
    ========================================================

    遇到：

        "("
            depth += 1

    遇到：

        ")"
            depth -= 1

    当：

        depth == 0

    表示最外层括号正式结束。


    ========================================================
    【还必须处理字符串】
    ========================================================

    SQL：

        ('abc)def')

    字符串中的 ")"：

        不是 SQL 括号。

    所以进入 quote 后，
    必须暂时停止括号计数。
    """

    if (
        start >= len(sql)
        or sql[start] != "("
    ):
        return None

    cursor = start

    depth = 0

    # quote=None：
    #
    # 当前不在：
    #
    #     '...'
    #     "..."
    #     `...`
    #
    # 中。
    quote: str | None = None

    while cursor < len(sql):

        char = sql[
            cursor
        ]

        # ----------------------------------------------------
        # 当前正在 quoted content 中。
        # ----------------------------------------------------

        if quote is not None:

            # ------------------------------------------------
            # SQL 常见 doubled quote：
            #
            #     'it''s'
            #
            # 中间两个 '：
            #
            #     不代表字符串结束。
            # ------------------------------------------------

            if char == quote:

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

                # 真正关闭 quote。
                quote = None

            cursor += 1

            continue

        # ----------------------------------------------------
        # 当前不在 quote。
        #
        # 如果遇到：
        #
        #     '
        #     "
        #     `
        #
        # 就进入 quoted content。
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
        # 跳过 -- line comment。
        #
        # comment 中即使有：
        #
        #     (
        #     )
        #
        # 也不能参与 depth 计算。
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
                return None

            cursor = (
                newline
                + 1
            )

            continue

        # ----------------------------------------------------
        # 同理跳过：
        #
        #     /* block comment */
        # ----------------------------------------------------

        if sql.startswith(
            "/*",
            cursor,
        ):

            comment_end = sql.find(
                "*/",
                cursor + 2,
            )

            if comment_end < 0:
                return None

            cursor = (
                comment_end
                + 2
            )

            continue

        # ----------------------------------------------------
        # 真正 SQL 括号开始。
        # ----------------------------------------------------

        if char == "(":

            depth += 1

        # ----------------------------------------------------
        # 真正 SQL 括号结束。
        # ----------------------------------------------------

        elif char == ")":

            depth -= 1

            # depth 回到 0：
            #
            # 说明 start 对应的最外层 "("
            # 已经找到匹配 ")"。
            if depth == 0:

                # 返回 ")" 后面的 offset。
                #
                # 这与 Python slicing 的半开区间一致：
                #
                #     sql[start:cursor + 1]
                return (
                    cursor
                    + 1
                )

        cursor += 1

    # 扫描到 SQL 结尾仍然没有 depth == 0。
    #
    # 表示当前括号没有闭合。
    return None