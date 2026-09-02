from __future__ import annotations

from dataclasses import dataclass


# Semantic Asset 中允许出现的原子值类型。
# 这里故意限制为 JSON/配置文件天然可表达的基础类型，不接受任意 Python 对象，
# 避免 SemanticModelLoader 把运行时对象或表达式实例带进“长期治理资产”边界。
SemanticScalar = (
    str
    | int
    | float
    | bool
    | None
)

# IN / BETWEEN 等过滤条件可能需要多个值，因此在原子值之外允许 tuple。
# Loader 会把 JSON list 统一转换为 tuple，使整个 Semantic Model 保持 frozen/不可变语义。
SemanticFilterValue = (
    SemanticScalar
    | tuple[
        SemanticScalar,
        ...
    ]
)


@dataclass(frozen=True)
class SemanticFilter:
    """
    Semantic Asset 中声明的“指标固定过滤条件”。

    【架构位置】
    Semantic Asset -> SemanticMetric.fixed_filters -> MetricSQLCompiler -> WHERE AST

    例如：某个“高新技术企业贷款余额”指标如果治理口径要求固定满足
    ``is_high_tech = '1'``，这个条件属于指标定义本身，而不是用户每次查询时临时提供的过滤。

    【与 QueryPlan.filters 的区别】
    - SemanticFilter：长期治理确认的指标事实；
    - QueryPlan.filters：Planner 根据当前用户问题形成的任务级过滤。

    Compiler 会把两类过滤最终合并到 WHERE，但来源和审计含义不能混为一谈。
    """

    # 必须是 SemanticMetric.table 对应物理表中真实存在的字段名。
    column: str

    # 使用结构化操作符文本，例如 = / >= / in / between。
    # Compiler 仍会做白名单映射，Semantic Asset 本身不能绕过执行安全边界。
    operator: str

    # 操作符对应的治理值。IN/BETWEEN 通常使用 tuple，其余比较通常使用标量。
    value: SemanticFilterValue

    def __post_init__(
        self,
    ) -> None:
        # 空 column 无法形成可审计、可验证的固定过滤，因此在资产 Contract 边界立即拒绝。
        if not self.column.strip():
            raise ValueError(
                "SemanticFilter.column "
                "cannot be empty."
            )

        # operator 为空时 Compiler 无法判断过滤语义，也不应在运行时猜测默认操作符。
        if not self.operator.strip():
            raise ValueError(
                "SemanticFilter.operator "
                "cannot be empty."
            )


@dataclass(frozen=True)
class SemanticColumn:
    """
    语义表中的字段级资产。

    当前对象主要服务 Semantic Context Render 与 Schema Linking：它描述字段的业务含义、
    类型和同义词，但不替代 Physical Metadata。最终某列是否真实存在仍必须由 MetadataProvider
    / LinkedSchema 确认。
    """

    name: str
    description: str
    data_type: str = ""
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticTable:
    """
    一个业务可查询表的语义资产描述。

    name 是语义资产中约定的表标识；columns 描述业务字段；synonyms 用于自然语言匹配；
    grain 表示数据粒度。它们用于帮助 Planner/Linker理解业务，但不能替代真实物理元数据。
    """

    name: str
    description: str
    columns: tuple[SemanticColumn, ...]

    synonyms: tuple[str, ...] = ()
    grain: str = ""


@dataclass(frozen=True)
class SemanticMetric:
    """
    Governed Metric Asset（治理后的指标资产）。

    【为什么同时保留 expression 与 aggregation/source_column】

    ``expression`` 是完整业务表达式，例如：
        SUM(loan_bal_rmb)
        SUM(balance * rate) / SUM(balance)

    它适合：
    - Prompt / LLM SQLGenerator；
    - LLM Reviewer；
    - 复杂指标表达；
    - 后续更高级的语义解释。

    ``aggregation + source_column`` 则只表达可形式化的“简单指标”：
        aggregation = "sum"
        source_column = "loan_bal_rmb"

    Phase 4.1 MetricSQLCompiler 只消费这种可确定性证明的简单结构，而不会重新解析 expression
    去“猜”指标是否等价于某个聚合。这样可以保持 Compiler 的确定性边界。

    【fixed_filters】
    指标口径固有的治理过滤。例如“绿色贷款余额”可能要求一个固定业务标志位。
    Compiler 必须自动带入这些过滤，不能依赖 Planner 每次重复生成。

    【default_dimensions】
    为查询设计/Planner 提供指标常用维度提示；它不是 SQL GROUP BY 的自动强制规则。

    【table】
    当前字段继续承担 source_table 的职责。技术方案没有要求做公共 Contract 重命名，
    因此这里保留既有命名，避免无价值迁移。

    注意：本对象只定义“资产结构 Contract”，不负责判断资产内容是否正确。
    Semantic Asset 的准确性盘点仍属于后续独立治理工作。
    """

    name: str
    description: str
    expression: str

    # 指标所属的唯一源表标识。Metric Compiler V1 只支持单物理表。
    table: str

    synonyms: tuple[str, ...] = ()

    # 简单指标的聚合类型；None 表示不能通过该结构直接确定性编译。
    aggregation: str | None = None

    # 简单指标直接聚合的源列；None 通常意味着需要 expression-level / LLM 生成。
    source_column: str | None = None

    # 无论用户问什么，只要使用该指标就必须成立的治理过滤条件。
    fixed_filters: tuple[SemanticFilter, ...] = ()

    # 指标常见展示/分析维度提示，不自动改变 QueryPlan。
    default_dimensions: tuple[str, ...] = ()

    # 展示与解释用单位，例如 元、户、%。不参与 Metric Compiler SQL 结构生成。
    unit: str = ""

    def __post_init__(
        self,
    ) -> None:
        # name 是 QueryPlan.metrics 与 SemanticModel.get_metric() 的稳定查找键。
        if not self.name.strip():
            raise ValueError(
                "SemanticMetric.name "
                "cannot be empty."
            )

        # 没有 source table 的指标无法进入 Schema Linking / Compiler 的物理事实链。
        if not self.table.strip():
            raise ValueError(
                "SemanticMetric.table "
                "cannot be empty."
            )

        # expression 仍然是指标完整口径的必填事实，即使简单指标另有结构化字段也必须保留。
        if not self.expression.strip():
            raise ValueError(
                "SemanticMetric.expression "
                "cannot be empty."
            )

        # None 合法，代表“不提供简单编译结构”；空字符串不合法，因为它会制造真假难辨的半状态。
        if (
            self.aggregation is not None
            and not self.aggregation.strip()
        ):
            raise ValueError(
                "SemanticMetric.aggregation "
                "cannot be blank."
            )

        if (
            self.source_column is not None
            and not self.source_column.strip()
        ):
            raise ValueError(
                "SemanticMetric.source_column "
                "cannot be blank."
            )


@dataclass(frozen=True)
class SemanticModel:
    """
    一个 Domain 当前加载后的只读 Semantic Asset Snapshot。

    它是长期资产容器，不是单次 QueryContext。Runtime 每次查询会把 SemanticModel 渲染/检索成
    Task Context，同时 Trust Evidence 可以保留结构化模型用于确定性规则校验。
    """

    tables: tuple[SemanticTable, ...]
    metrics: tuple[SemanticMetric, ...] = ()

    def get_table(
        self,
        table_name: str,
    ) -> SemanticTable | None:
        """按不区分大小写的稳定名称查找语义表；找不到时返回 None，不在这里抛异常。"""

        normalized = table_name.strip().lower()

        for table in self.tables:
            if table.name.lower() == normalized:
                return table

        return None

    def get_metric(
        self,
        metric_name: str,
    ) -> SemanticMetric | None:
        """
        按治理指标 name 做精确、大小写不敏感查找。

        synonyms 的自然语言解析属于 Planner / Semantic Retrieval，不应该在这个基础容器方法中
        隐式做模糊匹配，否则同一个名字可能在不同调用方得到不同结果。
        """

        normalized = (
            metric_name
            .strip()
            .lower()
        )

        for metric in self.metrics:
            if (
                metric.name.lower()
                == normalized
            ):
                return metric

        return None