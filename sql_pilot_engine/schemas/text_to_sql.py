from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.generation.models import (
    QueryPlan,
)
from sql_pilot_engine.linking.models import (
    SchemaLinkingFailure,
)


@dataclass(frozen=True)
class TextToSQLRequest:
    """
    Text-to-SQL Capability 的公开请求 DTO。

    这是 Application Boundary，不是 Runtime State：调用方只需要提供用户问题、目标 SQL 方言
    和可选 session context，不需要知道 LangGraph thread / turn / checkpoint 等内部实现。
    """

    question: str
    dialect: str = "maxcompute"
    session_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # 空问题无法进入 Planning，直接在公开 Contract 边界拒绝，比进入 Graph 后失败更清晰。
        if not self.question.strip():
            raise ValueError(
                "TextToSQLRequest.question cannot be empty."
            )

        # session_context 的每一项都应该是有意义的上下文片段，避免把纯空白送入 Prompt。
        if any(
            not item.strip()
            for item in self.session_context
        ):
            raise ValueError(
                "session_context cannot contain empty items."
            )


@dataclass(frozen=True)
class TextToSQLResult:
    """
    Text-to-SQL 成功/失败终态的公开 Application DTO。

    【为什么这里同时保留 generated_sql 与 trusted_sql】
    ``generated_sql != trusted_sql`` 是项目的核心可观测不变量：前者是 Generation Candidate，
    后者是 Trust + Semantic Validation 后最终接受的 SQL。即使两段文本当前相同，也不能合并。

    【Phase 4.1 新增字段】
    - generation_source：当前最终 Candidate 来自 Compiler 还是 LLM；
    - compilation_status：本轮是否被 Metric Compiler 成功编译；
    - compilation_fallback_reason：未编译时的正常 fallback 诊断；
    - compilation_evidence：编译成功时的稳定 Application Projection。

    这些字段是观测/审计信息，不改变 ``success`` 的产品语义。Compiler fallback 后 LLM 最终
    成功时，success 仍然可以为 True。
    """

    question: str
    query_plan: QueryPlan
    generated_sql: str
    trusted_sql: str | None
    success: bool

    # 当前 SQL Candidate 的真实生成来源：compiled / llm。
    generation_source: str | None = None

    # Compiler 尝试结果：compiled / not_compilable。未到达 Compiler 的流程可为 None。
    compilation_status: str | None = None

    # 只有 not_compilable 时有值；它是正常能力边界诊断，不等同于 failure_type。
    compilation_fallback_reason: str | None = None

    # 只在 Compiler 成功时存在。Application DTO 与内部 CompilationEvidence 故意分离。
    compilation_evidence: TextToSQLCompilationEvidence | None = None

    # Schema Linking 的 typed failure 保留给调用方做精确诊断。
    linking_failures: tuple[
        SchemaLinkingFailure,
        ...
    ] = ()

    linking_error_message: str | None = None

    # SQL Trust 层结果。"not_run" 表示流程在 Trust 之前已经结束。
    validation_status: str = "not_run"
    validation_error_message: str | None = None
    validation_issues: tuple[
        TextToSQLValidationIssue,
        ...
    ] = ()

    # Semantic Validation 与 SQL Trust 是独立层，因此单独暴露状态与问题。
    semantic_validation_status: str | None = None
    semantic_missing_requirements: tuple[str, ...] = ()
    semantic_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class TextToSQLClarification:
    """
    Text-to-SQL 需要 Human-in-the-loop 时的公开响应 DTO。

    它与 TextToSQLResult 是互斥响应类型。thread_id 必须回给调用方，后续才能通过
    TextToSQLCapability.resume() 恢复同一个 LangGraph checkpoint。
    """

    question: str
    clarification_question: str
    thread_id: str | None = None
    missing_context: tuple[str, ...] = ()
    reason: str = ""


# Capability 对外只有“结果”或“需要澄清”两类响应，不把 Runtime 内部状态直接暴露出去。
TextToSQLResponse = TextToSQLResult | TextToSQLClarification


@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLValidationIssue:
    """
    Text-to-SQL 对内部 SQL Trust Issue 的稳定 Application Projection。

    为什么不直接返回 ReviewResult / Issue：
    - 内部 Review DTO 可能随着 Trust Workflow 演进；
    - Capability 调用方只需要稳定的 rule/source/severity/action/category/message/evidence；
    - Application Boundary 应阻止内部领域对象向外泄漏。
    """

    rule_id: str
    source: str
    severity: str
    action: str
    category: str
    message: str
    evidence: str

    def __post_init__(self) -> None:
        # rule_id 是 Issue 的稳定身份，没有它就无法可靠统计或审计。
        if not self.rule_id.strip():
            raise ValueError(
                "rule_id cannot be empty"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class TextToSQLCompilationEvidence:
    """
    内部 CompilationEvidence 在 Application Boundary 的稳定投影。

    这里故意重新定义 DTO，而不是把 ``generation.models.CompilationEvidence`` 直接暴露给
    外部调用方。这样下一阶段即使 Compiler 内部增加 AST/debug 字段，也不会无意扩张公开 API。

    字段语义与内部 Evidence 对齐：指标 -> 物理表 -> 聚合表达式 -> 维度 -> 过滤 -> GROUP BY。
    """

    metric_names: tuple[str, ...]
    physical_table: str
    metric_expressions: tuple[str, ...]
    dimension_columns: tuple[str, ...] = ()
    filter_expressions: tuple[str, ...] = ()
    group_by_columns: tuple[str, ...] = ()