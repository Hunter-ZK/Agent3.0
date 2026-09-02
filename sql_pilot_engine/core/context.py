"""
SQL Review 单次运行的共享 ReviewContext。

【架构位置】
SQLExecutionContext / Request
    -> SQLAnalysisAdapter
    -> ReviewContext
    -> Deterministic Rule / Metadata Validation / LLM Review

【为什么需要 ReviewContext】
同一条 SQL 在一次 Review 中会被多种规则、Metadata Validator 和 LLM Reviewer 读取。
如果每个组件都重新解析 SQL、重新创建 Provider 或各自维护证据，就会产生重复计算和事实漂移。
ReviewContext 因此只保存“这一次审查已经准备好的共享对象引用”。

【重要边界】
- QueryContext 是用户任务的业务上下文；ReviewContext 是 SQL Review 阶段的内部运行上下文；
- SQLTrustEvidence 是 Planner/Linker/Semantic Asset 提供的任务级证据；SQLFacts 是 SQL 自身客观事实；
- ReviewContext 不负责生成这些事实，也不决定最终 Workflow 路由；
- Rule 只能读取 context 中的事实，不应修改其它 Rule 将要读取的分析结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:
    # TYPE_CHECKING 下的导入只服务静态类型检查，避免运行期不必要的循环依赖。
    from sql_pilot_engine.analysis.facts import SQLFacts
    from sql_pilot_engine.analysis.sql_parser import SQLParseResult
    from sql_pilot_engine.metadata.provider import MetadataProvider
    from sql_pilot_engine.core.trust_evidence import SQLTrustEvidence


@dataclass
class ReviewContext:
    """规则和审查能力共享的单次运行上下文。"""

    # 运行模式与产品层 SQL 方言。具体 SQLGlot 方言映射不在 Core 中处理。
    mode: str = "prod"
    dialect: str = "maxcompute"

    # SQL Analysis 阶段产物。parse_result 记录 AST/解析状态；sql_facts 记录客观结构事实。
    parse_result: SQLParseResult | None = None
    sql_facts: SQLFacts | None = None

    # MetadataProvider 是查询物理元数据的能力接口；是否启用由上层 Workflow/ExecutionContext 决定。
    metadata_provider: MetadataProvider | None = None

    # Text-to-SQL 等调用方可提供任务级 Trust Evidence；独立 SQL Review 场景允许为 None。
    trust_evidence: SQLTrustEvidence | None = None

    # 是否允许进入 LLM Review。Deterministic Gate 不依赖这个开关。
    enable_llm: bool = False
    llm_provider: str = "mock"

    # Rule Pack 用于按 Capability 选择确定性规则集合，避免把所有规则无差别运行。
    rule_packs: tuple[str, ...] = ()

    # extra 只承载尚未形成稳定 Contract 的扩展运行信息；核心事实不应长期塞进该字典。
    extra: dict[str, Any] | None = None
