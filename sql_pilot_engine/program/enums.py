from __future__ import annotations

from enum import Enum


class ProgramAnalysisStatus(str, Enum):
    """
    SQL Program 分析的完成状态。

    COMPLETE:
        当前阶段要求的结构证据均已获得。

    PARTIAL:
        已建立 SQLProgram，但部分结构无法可靠分析。

    FAILED:
        无法建立可靠的 SQLProgram。
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class StatementKind(str, Enum):
    """
    Program 中单条业务 SQL Statement 的类型。

    SET 已由 ProgramPreprocessor 分离为 SessionHint，
    因此不属于这里的 Statement。
    """

    SELECT = "select"
    INSERT_OVERWRITE = "insert_overwrite"
    INSERT_INTO = "insert_into"
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"
    CREATE = "create"
    OTHER = "other"


class WriteStrategy(str, Enum):
    """目标表写入策略。"""

    OVERWRITE = "overwrite"
    APPEND = "append"


class ParameterUsageKind(str, Enum):
    """
    DataWorks / MaxCompute 调度参数在 Program 中的用途。

    A1 只识别 occurrence；
    Program Analysis 才负责判断 usage。
    """

    READ_PARTITION_FILTER = "read_partition_filter"
    WRITE_PARTITION = "write_partition"
    PERIOD_CLASSIFICATION = "period_classification"
    DATE_ARITHMETIC = "date_arithmetic"
    OTHER = "other"