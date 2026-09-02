"""
SQL Core 一次执行的共享参数容器。

【架构位置】
Capability / App Request
    -> SQLExecutionContext
    -> SQL Core Engine / TrustedSQLWorkflow
    -> ReviewContext / Services

【为什么需要这一层】
SQL Core 会同时消费 SQL 文本、方言、Metadata 开关、LLM 开关、Rule Pack、Fix 配置和任务级证据。
如果这些参数作为十几个独立参数在 Service/Workflow 之间传递，Contract 很快会失控。
SQLExecutionContext 因此负责把“一次 SQL Core 调用的执行参数”集中成一个对象。

【与其它 Context 的区别】
- QueryContext：当前用户问题的业务上下文快照；
- SQLTrustEvidence：Planner + LinkedSchema + SemanticModel 形成的可信任务证据；
- SQLExecutionContext：SQL Core 的执行配置与运行状态容器。

本对象不重新生成 QueryContext，也不把 SQLFacts 存进自己；SQLFacts 仍由 SQLAnalysisAdapter 生成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    # 仅类型检查时导入，避免 Core 与 Context/Generation 在运行期形成循环依赖。
    from sql_pilot_engine.context.builder import QueryContext
    from sql_pilot_engine.core.trust_evidence import SQLTrustEvidence


@dataclass
class SQLExecutionContext:
    """SQL Core 内部一次执行的共享运行上下文。"""

    # 最核心输入：待分析/审查/修复的 SQL 文本。
    sql: str

    # SQL 来源位置。内存调用默认 <memory>，文件审查场景可以写入真实路径用于报告定位。
    file_path: str = "<memory>"

    # prod/dev 等运行模式；具体模式含义由上层应用约定，Core 不自行推断。
    mode: str = "prod"

    # 产品层 SQL 方言名；SQLGlot 映射统一由 dialect adapter 处理。
    dialect: str = "maxcompute"

    # 可选规则分类过滤。None 表示不额外按 category 限制。
    categories: set[str] | None = None

    # Metadata 校验显式开关。关闭时 metadata_provider 即使存在也不应被误当成“必须校验”。
    enable_metadata: bool = False
    metadata_provider: Any | None = None

    # Text-to-SQL 等上游可注入任务级证据；独立 SQL Review 允许为空。
    trust_evidence: SQLTrustEvidence | None = None

    # LLM 是增强审查能力而不是 Deterministic Gate 的前提，因此独立开关。
    enable_llm: bool = False
    llm_provider: str = "mock"

    # 当前 Capability 希望启用的规则包，例如 text_to_sql；避免所有规则无差别执行。
    rule_packs: tuple[str, ...] = ()

    # 是否进入修复流程，以及修复 Provider 选择。
    fix_sql: bool = False
    fix_provider: str = "auto"

    # trace_id 标识一次 SQL Core 调用，便于日志、Evaluation 和未来 Observability 串联。
    trace_id: str = field(default_factory=lambda: str(uuid4()))

    # Workflow 重试计数。它是 SQL Core 的执行状态，不等同于 Text-to-SQL Runtime 的 generation_attempt。
    retry_count: int = 0

    # 上游 RAG/Knowledge Retrieval 已取得的文档；Core 只消费，不负责检索。
    retrieved_docs: list[dict[str, Any]] = field(default_factory=list)

    # Critic 对上一轮结果的反馈，供后续修复/重审使用。
    critic_feedback: list[str] = field(default_factory=list)

    # 与原始用户任务相同的 QueryContext 对象引用；不在 SQL Core 内部复制或重新构建。
    query_context: QueryContext | None = None
