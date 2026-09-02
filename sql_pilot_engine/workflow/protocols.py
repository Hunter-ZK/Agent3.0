from __future__ import annotations

from typing import Any, Protocol

from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.core.trust_evidence import (
    SQLTrustEvidence,
)


class TrustedSQLWorkflowResultView(Protocol):
    """
    Runtime 对 Trusted SQL Workflow 结果真正依赖的最小只读 Contract。

    【为什么这里使用 Protocol，而不是直接依赖 TrustedSQLWorkflowResult】
    QueryRuntimeNodes / TextToSQLStageService 只需要读取少量稳定字段，并不应该耦合
    TrustedSQLWorkflow 内部所有调试、Explain、Fix、Critic、Optimization 响应对象。
    使用结构化 Protocol 后：
    - 正式实现只要提供这些属性即可；
    - 测试 Fake / Stub 不需要构造完整生产 DTO；
    - Workflow 内部未来扩展字段时，不会把 Runtime 一起拖进重构。

    这也是 Agent3.0 的一个重要边界：Runtime 依赖“能力接口”，而不是某个具体实现类。
    """

    # Trust 子工作流是否接受当前 SQL Candidate。
    success: bool

    # 机器可读的最终状态，例如 no_issue / blocked / context_required / fix_verified。
    final_status: str

    # 被 Trust Workflow 接受后的 SQL；success=True 时 Runtime 要求该字段存在。
    trusted_sql: str | None

    # 失败或需要人工/上下文处理时的诊断信息。
    error_message: str | None

    # CONTEXT_REQUIRED 路由需要回传给 HITL 的缺失业务上下文。
    missing_context: tuple[str, ...]

    # Application 层真正需要暴露的最终 Review Issue 投影。
    # 使用 dict 是为了不把内部 Issue DTO 泄漏到 Runtime Protocol。
    validation_issues: tuple[
        dict[str, Any],
        ...
    ]


class TrustedSQLWorkflowPort(Protocol):
    """
    Text-to-SQL StageService 对“SQL 可信化子工作流”依赖的最小接口。

    【调用关系】
    QueryRuntimeNodes.trust_sql
        -> TextToSQLStageService.trust_sql
        -> TrustedSQLWorkflowPort.run
        -> 正式 TrustedSQLWorkflow / 测试 Fake

    StageService 通过这个 Port 传入 QueryContext、SQLTrustEvidence 和 capability rule pack，
    但不负责 Trusted SQL 内部的 review/fix/re-review/critic 编排。

    Phase 4.1 新增 ``enable_llm`` 的原因：
    Metric Compiler 已经在结构化事实基础上确定性生成 SQL。对这种 Candidate，初始 Trust
    仍必须执行 deterministic rules / metadata / evidence 检查，但可以显式关闭 LLM Review，
    避免模型再次“改写”一个已经由 Compiler 确定的结果。

    ``None`` 不是 False：
    - None：不覆盖 Workflow 自己的 default_enable_llm；
    - False：调用方明确要求本次关闭 LLM；
    - True：调用方明确要求本次开启 LLM。
    因此 LLM 生成路径应继续传 None，而不是把系统默认策略硬编码在 StageService。
    """

    def run(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
        query_context: QueryContext | None = None,
        trust_evidence: SQLTrustEvidence | None = None,
        rule_packs: tuple[str, ...] = (),
        enable_llm: bool | None = None,
    ) -> TrustedSQLWorkflowResultView:
        ...