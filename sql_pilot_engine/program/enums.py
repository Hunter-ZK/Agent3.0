from __future__ import annotations

from enum import Enum


class ProgramAnalysisStatus(
    str,
    Enum,
):
    """
    SQL Program 分析完整度。

    COMPLETE:
        当前 Program Analysis 声称支持的结构均已成功分析。

    PARTIAL:
        已得到部分可信结构，但存在无法解析或无法证明的区域。

    FAILED:
        Program 无法形成可用的结构模型。

    关键纪律：
    PARTIAL 不能被上层解释成 COMPLETE，
    UNKNOWN 也不能被转换成 False。
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class StatementKind(
    str,
    Enum,
):
    """
    Program 层 statement 的稳定类型。

    这里不直接暴露 SQLGlot Expression 类型，
    避免 Program Domain DTO 与第三方 AST Contract 绑定。
    """

    SELECT = "select"

    INSERT_OVERWRITE = (
        "insert_overwrite"
    )

    INSERT_INTO = "insert_into"

    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"
    CREATE = "create"

    OTHER = "other"


class WriteStrategy(
    str,
    Enum,
):
    """
    SQL Program 对目标表的写入策略。
    """

    OVERWRITE = "overwrite"
    APPEND = "append"


class ParameterUsageKind(
    str,
    Enum,
):
    """
    调度参数在 SQL Program 中承担的语义角色。

    注意：
    这是 SQL 结构用途，不是业务含义。

    例如：

        WHERE dt = '${p_month_yyyymm}'
            -> READ_PARTITION_FILTER

        PARTITION (
            dt='${p_month_yyyymm}'
        )
            -> WRITE_PARTITION

        CASE WHEN dt='${p_month_yyyymm}'
        THEN 'bq'
            -> PERIOD_CLASSIFICATION

        '${p_month_yyyymm}' - 1
            -> DATE_ARITHMETIC
    """

    READ_PARTITION_FILTER = (
        "read_partition_filter"
    )

    WRITE_PARTITION = (
        "write_partition"
    )

    PERIOD_CLASSIFICATION = (
        "period_classification"
    )

    DATE_ARITHMETIC = (
        "date_arithmetic"
    )

    OTHER = "other"