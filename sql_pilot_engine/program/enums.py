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


    
class SourceBindingKind(str, Enum):
    """
    SQL Scope 中一个 source alias 的绑定类型。

    PHYSICAL_TABLE:
        alias 绑定真实物理表。

    SCOPE:
        alias 绑定 SQLProgram 内部的另一个 Scope，
        例如 CTE / derived query / subquery。

    UNRESOLVED:
        Analyzer 知道当前存在这个 source alias，
        但暂时无法可靠确定它指向哪个物理表或 Scope。

    UNRESOLVED 是显式降级状态，不等同于错误，
    但它会使 ProgramAnalysisStatus 从 COMPLETE
    降级为 PARTIAL。
    """

    PHYSICAL_TABLE = "physical_table"
    SCOPE = "scope"
    UNRESOLVED = "unresolved"
    
