from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class QueryPlan:
    """
    Planner 输出的“逻辑查询计划”。

    【架构位置】
    User Question -> QueryPlanner -> QueryPlan -> SchemaLinker / MetricSQLCompiler / SQLGenerator

    这个对象只描述“用户想查什么”，不承诺任何字段已经在物理元数据中存在。
    因此：
    - tables / dimensions / metrics / group_by 是逻辑层名称；
    - filters 是 Planner 已经结构化到 SQL 条件形态的过滤文本，但仍必须由后续组件验证；
    - requirements 保存不能自然落进其它字段、但后续生成/语义校验仍需关注的业务要求。

    QueryPlan 不是 Semantic Truth，也不是 LinkedSchema。Planner 不应该在这里绕过
    SchemaLinker 直接“发明”物理字段，否则 Planning 与 Physical Resolution 的边界会失效。
    """

    tables: tuple[str, ...]
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    filters: tuple[str, ...] = ()
    group_by: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanningClarification:
    """
    Planner 无法安全形成 QueryPlan 时的显式澄清结果。

    这里使用独立 DTO，而不是用异常表达“业务信息不足”。原因是缺少时间范围、
    指标口径或业务限定通常属于正常对话分支，Runtime 需要把它路由到 HITL，
    而不是把它当成系统故障。
    """

    clarification_question: str
    missing_context: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        # 空问题无法形成可执行的 Human-in-the-loop 交互，因此在 Contract 边界立即拒绝。
        if not self.clarification_question.strip():
            raise ValueError(
                "clarification_question cannot be empty"
            )


# Planner 只有两种合法输出：
# 1. QueryPlan：信息足够，可以继续 Schema Linking；
# 2. PlanningClarification：信息不足，Runtime 必须转入澄清。
QueryPlanningOutcome = QueryPlan | PlanningClarification


@dataclass(frozen=True)
class GeneratedSQL:
    """
    Generation Stage 统一的 SQL Candidate Contract。

    无论 SQL 来自 LLM SQLGenerator，还是来自 MetricSQLCompiler，进入后续 Trusted SQL
    Workflow 前都必须统一成 GeneratedSQL。这样 Trust 层不需要理解“SQL 是怎么产生的”。

    dialect 保留 Agent3.0 产品层方言名称（例如 maxcompute），不暴露 SQLGlot 内部为了
    兼容解析而使用的 hive 等实现细节。
    """

    sql: str
    dialect: str

    def __post_init__(self) -> None:
        # 空 SQL 不是一个可进入 Trust Gate 的 Candidate，尽早在 DTO 层阻断。
        if not self.sql.strip():
            raise ValueError(
                "GeneratedSQL.sql cannot be empty."
            )


class CompilationStatus(str, Enum):
    """
    Metric Compiler 的二态结果。

    COMPILED 表示当前输入完全落在确定性编译能力边界内；
    NOT_COMPILABLE 表示当前输入超出 V1 Compiler 能力，应正常回退到 LLM Generator。

    注意：NOT_COMPILABLE 不是 Text-to-SQL 失败，也不是系统异常。
    """

    COMPILED = "compiled"
    NOT_COMPILABLE = "not_compilable"


class GenerationSource(str, Enum):
    """
    当前 SQL Candidate 的真实生成来源。

    这个字段是 Runtime / Evaluation 的可观测事实，不是质量结论：
    - COMPILED：由 MetricSQLCompiler 确定性生成；
    - LLM：由 SQLGenerator 模型生成，包含 Compiler fallback 后的正常路径。

    后续 Trust 策略会读取该来源：编译路径可关闭 LLM Review，但仍必须经过同一个
    Deterministic Trust Core，不能因为“是编译出来的”就跳过可信 SQL 验证。
    """

    COMPILED = "compiled"
    LLM = "llm"


class CompilationFallbackReason(str, Enum):
    """
    Metric Compiler V1 无法确定性编译时的诊断原因。

    这些枚举用于 Runtime 观测与 Evaluation 统计，不应该直接被解释成产品失败分类。
    例如 COMPLEX_EXPRESSION 只意味着“交给 LLM 更合适”，并不意味着最终查询失败。
    """

    # QueryPlan 没有指标；当前 Metric Compiler 不负责纯明细查询。
    NO_METRIC = "no_metric"

    # QueryPlan 或 LinkedSchema 涉及多张表，需要 JOIN/跨表语义。
    MULTI_TABLE = "multi_table"

    # 指标不能表示为 V1 支持的“单列 + 简单聚合”。
    COMPLEX_EXPRESSION = "complex_expression"

    # SemanticMetric 声明了 V1 白名单之外的聚合方式。
    UNSUPPORTED_AGGREGATION = "unsupported_aggregation"

    # Planner filter / metric fixed filter 超出安全白名单或无法验证。
    UNSUPPORTED_FILTER = "unsupported_filter"

    # Schema Linking 没有提供唯一、可验证的物理绑定。
    UNRESOLVED_SCHEMA = "unresolved_schema"

    # dimensions 与 group_by 不满足 V1 的严格一一对应约束。
    INVALID_GROUPING = "invalid_grouping"


@dataclass(frozen=True)
class CompilationEvidence:
    """
    Metric Compiler 的确定性生成证据。

    【为什么必须单独保存 Evidence】
    最终 SQL 文本只能告诉我们“生成了什么”，不能完整回答“为什么这样生成”。
    CompilationEvidence 保存 Compiler 真实消费的结构化事实，使 Runtime、Evaluation、
    审计和后续 Artifact 能追踪：使用了哪些指标、哪张物理表、哪些过滤与分组。

    这里保存的是“编译事实”，不是 SQL Trust Issue，也不是 Semantic Validation 结论。
    三者职责不能混合。
    """

    # QueryPlan 中被成功解析并参与 SQL 构造的指标逻辑名。
    metric_names: tuple[str, ...]

    # LinkedSchema 唯一确认的目标物理表全名。
    physical_table: str

    # 实际写入 SELECT 的聚合表达式（不含指标 alias），便于审计口径。
    metric_expressions: tuple[str, ...]

    # dimensions 最终绑定到的物理列。
    dimension_columns: tuple[str, ...] = ()

    # fixed_filters 与 Planner filters 经安全编译后的真实 SQL 谓词。
    filter_expressions: tuple[str, ...] = ()

    # group_by 最终绑定到的物理列。
    group_by_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricCompilationOutcome:
    """
    MetricSQLCompiler 的稳定返回 Contract。

    这里刻意不用 ``GeneratedSQL | None`` 单独表达结果，因为调用方还需要明确区分：
    - 编译成功；
    - 当前能力不支持、应该正常 fallback；
    - 真正的编程/系统异常（应抛异常，而不是伪装成 fallback）。

    【状态不变量】
    COMPILED:
        generated_sql != None
        evidence != None
        fallback_reason == None

    NOT_COMPILABLE:
        generated_sql == None
        evidence == None
        fallback_reason != None

    __post_init__ 在对象创建时强制这些不变量，防止 Runtime 收到“半成功”状态后再猜。
    """

    status: CompilationStatus
    generated_sql: GeneratedSQL | None = None
    evidence: CompilationEvidence | None = None
    fallback_reason: CompilationFallbackReason | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status is CompilationStatus.COMPILED:
            # 成功状态必须同时具备 SQL Candidate 与可审计证据。
            if self.generated_sql is None:
                raise ValueError(
                    "COMPILED outcome must contain generated_sql."
                )

            if self.evidence is None:
                raise ValueError(
                    "COMPILED outcome must contain evidence."
                )

            # 成功与 fallback 原因互斥；同时出现说明上游构造逻辑已经自相矛盾。
            if self.fallback_reason is not None:
                raise ValueError(
                    "COMPILED outcome cannot contain fallback_reason."
                )
            return

        # 当前只有 COMPILED / NOT_COMPILABLE 两个枚举值，因此走到这里就是 fallback Contract。
        if self.generated_sql is not None:
            raise ValueError(
                "NOT_COMPILABLE outcome cannot contain generated_sql."
            )

        if self.evidence is not None:
            raise ValueError(
                "NOT_COMPILABLE outcome cannot contain evidence."
            )

        if self.fallback_reason is None:
            raise ValueError(
                "NOT_COMPILABLE outcome must contain fallback_reason."
            )

    @classmethod
    def compiled(
        cls,
        *,
        generated_sql: GeneratedSQL,
        evidence: CompilationEvidence,
    ) -> "MetricCompilationOutcome":
        """构造一个满足成功不变量的编译结果，避免调用方重复手写 status 字段。"""

        return cls(
            status=CompilationStatus.COMPILED,
            generated_sql=generated_sql,
            evidence=evidence,
        )

    @classmethod
    def fallback(
        cls,
        *,
        fallback_reason: CompilationFallbackReason,
        reason: str,
    ) -> "MetricCompilationOutcome":
        """
        构造一个正常 fallback 结果。

        reason 用于开发/评估诊断；稳定机器可读分类由 fallback_reason 提供。
        """

        return cls(
            status=CompilationStatus.NOT_COMPILABLE,
            fallback_reason=fallback_reason,
            reason=reason,
        )