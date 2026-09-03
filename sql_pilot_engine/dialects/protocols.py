from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(
    frozen=True,
    slots=True,
)
class CompatibilityEdit:
    """
    Dialect Compatibility Adapter 发现的一次文本修改。

    ========================================================
    【架构位置】
    ========================================================

    Analyzer SQL
        ↓
    DialectCompatibilityAdapter
        ↓
    CompatibilityEdit
        ↓
    ProgramPreprocessor
        ↓
    修改后的 Analyzer SQL


    ========================================================
    【这个对象表达什么】
    ========================================================

    它不是：

        “SQL 有一个错误”

    而是：

        “为了让当前 Analyzer 能理解这个方言，
         建议对 Analyzer SQL 做一次内部转换。”


    ========================================================
    【start / end】
    ========================================================

    使用 Python 标准半开区间：

        [start, end)

    例如想把：

        abc

    中的：

        b

    换成：

        B

    那么：

        start = 1
        end = 2
        replacement = "B"


    ========================================================
    【插入字符】
    ========================================================

    如果：

        start == end

    就表示不是替换原字符，而是在当前位置插入。

    例如：

        (1)
        (2)

    想在第一行 ")" 后插入逗号：

        start = 某个 offset
        end = 同一个 offset
        replacement = ","
    """

    start: int

    end: int

    replacement: str

    # Patch 的稳定 ID。
    #
    # 后面的日志、Evaluation、dialect gap 文档
    # 都可以使用这个 ID，而不是依赖自然语言描述。
    patch_id: str

    # False 表示：
    #
    # 我们只确认这个转换有助于 Analyzer，
    # 尚未证明原 SQL 在 MaxCompute 原生环境中的正式语义。
    native_verified: bool

    # 给人看的说明。
    description: str


class DialectCompatibilityAdapter(
    Protocol,
):
    """
    所有 SQL Dialect Compatibility Adapter 的公共接口。

    ========================================================
    【为什么使用 Protocol】
    ========================================================

    ProgramPreprocessor 不应该知道具体实现到底是：

        MaxComputeCompatibilityAdapter
        SparkCompatibilityAdapter
        HiveCompatibilityAdapter

    它只需要知道：

        “你只要有 collect_edits() 就可以。”

    所以 ProgramPreprocessor 依赖的是：

        接口

    而不是：

        某一个具体类。


    ========================================================
    【collect_edits() 做什么】
    ========================================================

    输入：

        当前 Analyzer SQL

    输出：

        需要做的 CompatibilityEdit

    Adapter 自己不直接修改 SQL。

    这是一个很重要的边界：

        Adapter
            ↓
        只负责“发现应该怎么改”

        ProgramPreprocessor
            ↓
        负责“真正执行修改 + 维护 SourceMap”

    这样 SourceMap 的修改逻辑只存在一个地方。
    """

    def collect_edits(
        self,
        sql: str,
    ) -> tuple[
        CompatibilityEdit,
        ...,
    ]:
        ...