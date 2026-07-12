# sql_review_agent/schemas/requests.py

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SQLReviewRequest:
    """外部调用 SQL Review Engine 的审查请求 DTO。

    设计目标：把 CLI / Web / Agent Workflow 的输入统一收口，避免外部调用方
    直接依赖 ReviewService.review_sql(...) 的长参数列表。
    """

    sql: str
    file_path: str = "<memory>"
    mode: str = "prod"
    dialect: str = "maxcompute"
    categories: set[str] | None = None
    enable_metadata: bool = False
    enable_llm: bool = False
    llm_provider: str = "mock"
    metadata_provider: Any | None = None
    trace_id: str | None = None


@dataclass
class SQLFixRequest(SQLReviewRequest):
    """外部调用 SQL Review Engine 的修复请求 DTO。

    Fix 不是绕开 Review，而是先 Review 再基于 issues 生成完整修复 SQL。
    """

    fix_provider: str = "auto"


@dataclass
class SQLExplainRequest(SQLReviewRequest):
    """SQL Explain 请求占位。

    C 阶段会把 Explain 纳入 LLM-first 单 Agent 闭环；B 阶段只保留契约位置。
    """

    pass


@dataclass
class SQLOptimizeRequest(SQLReviewRequest):
    """SQL Optimize 请求占位。

    C/D 阶段结合 LLM 与 RAG 后再实现真正优化建议。
    """

    optimization_goals: list[str] = field(default_factory=list)
