from __future__ import annotations

# SQLGlot 在本模块中承担两个职责：
# 1. 把 Planner 产生的过滤条件字符串解析为 AST，用于做结构级白名单校验；
# 2. 用 AST Builder 生成最终 SQL，避免手工字符串拼接。
#
# 这里刻意不使用字符串模板直接生成 SQL。原因不是“字符串一定不安全”，
# 而是 AST 能让我们对 SQL 结构做确定性的约束、验证和方言渲染，这正是
# Metric Compiler 与 LLM SQL Generator 的核心差异。
from sqlglot import (
    exp,
    parse,
)

# ParseError 只表示“输入过滤条件无法被 SQLGlot 解析”。
# 对 Metric Compiler 来说，这不是系统异常，而是当前输入超出了确定性编译能力，
# 因此捕获后应返回 NOT_COMPILABLE，让 Runtime 正常回退到 LLM Generator。
from sqlglot.errors import (
    ParseError,
)

# SemanticModel 是指标口径的结构化事实来源。
# Metric Compiler 不负责创建、修正或治理这些资产，只消费已经批准的资产。
from sql_pilot_engine.context.semantic.models import (
    SemanticFilter,
    SemanticMetric,
    SemanticModel,
)

# Metric Compiler 的输入/输出 Contract 全部放在 generation.models：
# - QueryPlan：Planner 已经解释好的业务查询意图；
# - GeneratedSQL：统一 SQL Candidate Contract；
# - CompilationEvidence：记录确定性编译依据；
# - MetricCompilationOutcome：统一表达“编译成功”或“可预期回退”。
from sql_pilot_engine.generation.models import (
    CompilationEvidence,
    CompilationFallbackReason,
    GeneratedSQL,
    MetricCompilationOutcome,
    QueryPlan,
)

# LinkedSchema 是 Schema Linking 的正式产物。
# Compiler 必须使用已经解析过的物理绑定，不能自己重新猜表、猜字段，
# 否则 Planner / SchemaLinker / Compiler 三层职责会重新混在一起。
from sql_pilot_engine.linking.models import (
    LinkedSchema,
    SchemaBindingKind,
)

# TableMetadata 用于做最后一层物理事实校验：
# 即使 SemanticMetric 和 SchemaBinding 都声称某列存在，也必须确认当前物理表元数据中真有该列。
from sql_pilot_engine.metadata.models import (
    TableMetadata,
)

# Agent3.0 的产品层 dialect 与 SQLGlot 支持的 dialect 不是完全一一对应。
# 例如产品层使用 maxcompute / odps / dataworks，而 SQLGlot 当前实际按 hive 语法解析、渲染。
# 这个映射必须统一走公共 resolver，不能在 Compiler 内部再维护一套映射表。
from sql_pilot_engine.dialects.sqlglot import (
    resolve_sqlglot_dialect,
)


class MetricSQLCompiler:
    """
    Simple Metric -> SQL 的确定性编译器（Deterministic Compiler）。

    【架构位置】

        User Question
            ↓
        QueryPlanner
            ↓
        QueryPlan                    —— 业务意图
            ↓
        SchemaLinker
            ↓
        LinkedSchema                 —— 物理绑定
            ↓
        MetricSQLCompiler            —— 本类：确定性 SQL Candidate
            ↓                         ↘ NOT_COMPILABLE
        Trusted SQL                     SQLGenerator(LLM)
            ↓                              ↓
        Semantic Validation          Trusted SQL

    也就是说，本类不是新的 Text-to-SQL Workflow，也不是另一个 Agent。
    它只是 Generation Stage 中的一条“高确定性快路径”：当 QueryPlan、SemanticModel、
    LinkedSchema 已经提供足够结构化事实时，不再让 LLM 重复猜测一个本可以直接计算出来的 SQL。

    【为什么要新增这一层，而不是继续全部交给 LLM】

    1. 确定性：
       对于 SUM(balance)、COUNT(DISTINCT customer_id) 这类已经结构化定义的指标，
       相同输入应该得到相同 SQL，不应受模型随机性影响。

    2. 可审计：
       Compiler 会产出 CompilationEvidence，明确记录指标、表、过滤、维度和 GROUP BY
       是依据哪些结构化事实生成的，而不是只留下最终 SQL 文本。

    3. 成本与延迟：
       能确定性生成的场景不需要再调用 SQL LLM，减少模型调用次数。

    4. 职责清晰：
       Planner 负责“用户想查什么”，SchemaLinker 负责“落到哪些物理资产”，
       Compiler 只负责“把已经确认的结构化事实降低成 SQL AST”。

    【V1 明确支持的能力】

    - 单物理表；
    - 一个或多个简单指标；
    - SUM / AVG / MIN / MAX / COUNT / COUNT DISTINCT；
    - 维度与 GROUP BY；
    - SemanticMetric.fixed_filters；
    - Planner 中简单、可安全验证的过滤条件；
    - 比较、IN、BETWEEN，以及 AND 组合。

    【V1 明确不支持的能力】

    - JOIN / 多表；
    - 子查询；
    - Window Function；
    - CASE WHEN；
    - 复杂指标 expression，例如加权平均、分子分母组合；
    - OR / LIKE / 函数调用 / 列间算术等复杂过滤；
    - 任何无法由 SchemaBinding 唯一确认的列。

    这些“不支持”不是错误，也不代表请求失败。Compiler 必须返回 NOT_COMPILABLE，
    由 Runtime 路由到已有 SQLGenerator(LLM)。只有真正违反编程 Contract 的情况才抛异常。
    """

    # 这不是“所有 SQL 聚合函数”的枚举，而是 V1 明确批准进入确定性编译路径的白名单。
    # 新增聚合类型时必须同时考虑：
    # - SemanticMetric Contract 是否能无歧义表达；
    # - SQLGlot AST 构造是否明确；
    # - 不同方言是否可稳定渲染；
    # - 测试与 CompilationEvidence 是否同步覆盖。
    _SUPPORTED_AGGREGATIONS = {
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "count_distinct",
    }

    def __init__(
        self,
        *,
        semantic_model: SemanticModel,
    ) -> None:
        """
        注入长期存在的 SemanticModel。

        Compiler 自身不维护请求级状态，因此同一个实例可以服务多个 QueryPlan。
        SemanticModel 由 Composition Root 加载后，同时注入 SchemaLinker 与 Compiler，
        这样两者消费的是同一份批准资产，而不是各自读取一份可能漂移的配置。
        """
        self._semantic_model = semantic_model

    # ========================================================
    # Public API
    # ========================================================

    def compile(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        dialect: str,
    ) -> MetricCompilationOutcome:
        """
        尝试把 QueryPlan + LinkedSchema 编译成确定性的 GeneratedSQL。

        【输入】
        plan:
            Planner 输出的逻辑查询计划。Compiler 不重新解释自然语言。
        linked_schema:
            SchemaLinker 输出的物理绑定。Compiler 不重新搜索元数据。
        dialect:
            产品层 SQL 方言，例如 maxcompute。最终 GeneratedSQL 仍保留这个产品方言；
            但内部交给 SQLGlot 解析/渲染前，会转换成 SQLGlot 真正支持的 dialect。

        【输出】
        - COMPILED：generated_sql 与 evidence 必须同时存在；
        - NOT_COMPILABLE：generated_sql/evidence 必须为空，并给出 fallback_reason。

        主流程采用 fail-closed 的确定性策略：任何一步出现歧义、复杂表达式或不受支持结构，
        都停止确定性编译并回退，而不是“尽量猜一个 SQL”。
        """

        # 1. SchemaLinker 没有完成唯一解析时，Compiler 没有资格继续猜物理字段。
        if not linked_schema.resolved:
            return self._fallback(
                CompilationFallbackReason.UNRESOLVED_SCHEMA,
                "LinkedSchema is unresolved.",
            )

        # 2. Phase 4.1 的 Compiler 是 Metric Compiler，不处理纯明细查询。
        #    没有 metric 的查询仍交给通用 SQLGenerator。
        if not plan.metrics:
            return self._fallback(
                CompilationFallbackReason.NO_METRIC,
                "QueryPlan contains no metric.",
            )

        # 3. 产品方言与 SQLGlot 方言解耦。
        #    例如 GeneratedSQL.dialect 仍是 maxcompute，但 parse/render 使用 hive。
        sqlglot_dialect = resolve_sqlglot_dialect(dialect)

        # 4. V1 只允许一个逻辑目标表、一个已解析物理表。
        #    任意一侧出现多表都意味着需要 JOIN 或跨表语义，立即回退给 LLM。
        if len(plan.tables) != 1 or len(linked_schema.tables) != 1:
            return self._fallback(
                CompilationFallbackReason.MULTI_TABLE,
                "Metric Compiler V1 supports one physical table only.",
            )

        # linked_schema.tables 保存的是绑定包装对象，真正用于字段验证的是 metadata。
        table = linked_schema.tables[0].metadata

        # 5. V1 要求 SELECT 中的业务维度与 GROUP BY 逻辑维度完全一致。
        #    这是故意收紧编译范围，而不是 SQL 标准的全部能力边界。
        if not self._validate_grouping(plan):
            return self._fallback(
                CompilationFallbackReason.INVALID_GROUPING,
                "Metric query dimensions must match group_by for deterministic compilation.",
            )

        # 6. 把逻辑维度解析成唯一物理列。
        #    一对多、跨表或元数据不存在都视为不能确定性编译。
        dimension_columns = self._resolve_dimension_columns(
            plan=plan,
            linked_schema=linked_schema,
            table=table,
        )
        if dimension_columns is None:
            return self._fallback(
                CompilationFallbackReason.UNRESOLVED_SCHEMA,
                "Dimension or group_by binding is unavailable.",
            )

        # 7. 编译指标 SELECT 表达式。
        #    返回 metric 对象本身，是因为后续仍需要读取每个指标绑定的 fixed_filters。
        (
            metric_selects,
            metric_expressions,
            metrics,
            metric_error,
        ) = self._compile_metrics(
            plan=plan,
            linked_schema=linked_schema,
            table=table,
            dialect=sqlglot_dialect,
        )

        if metric_error is not None:
            return metric_error

        # WHERE 条件统一先构造为 AST，最后再用 AND 合并。
        # 这样 fixed_filters 与 Planner filters 走同一种 SQL 构造方式，不做字符串拼接。
        predicates: list[exp.Expression] = []

        # --------------------------------------------------------
        # 8-a. Metric Fixed Filters
        # --------------------------------------------------------
        # fixed_filters 属于指标定义本身，例如“高新技术企业贷款余额”可能固定要求
        # is_high_tech_mfg_loan_code = '1'。它们不是用户可选过滤，而是指标口径的一部分。
        for metric in metrics:
            for fixed_filter in metric.fixed_filters:
                predicate = self._build_semantic_filter(
                    semantic_filter=fixed_filter,
                    table=table,
                )
                if predicate is None:
                    return self._fallback(
                        CompilationFallbackReason.UNSUPPORTED_FILTER,
                        f"Metric fixed filter cannot be compiled: {fixed_filter.column} {fixed_filter.operator}",
                    )
                predicates.append(predicate)

        # --------------------------------------------------------
        # 8-b. Planner Filters
        # --------------------------------------------------------
        # QueryPlan.filters 当前仍是字符串 Contract，因此不能直接 `AND`.join()。
        # 每个字符串必须先 parse 成 AST，再通过严格白名单验证列、操作符和值结构。
        for filter_text in plan.filters:
            predicate = self._parse_plan_filter(
                filter_text=filter_text,
                dialect=sqlglot_dialect,
                table=table,
            )
            if predicate is None:
                return self._fallback(
                    CompilationFallbackReason.UNSUPPORTED_FILTER,
                    f"Planner filter is outside the compiler safe subset: {filter_text}",
                )
            predicates.append(predicate)

        # fixed_filter 与 Planner filter 可能表达同一条件。
        # 去重只用于减少冗余，不改变语义，也不作为安全判定依据。
        predicates = self._dedupe_predicates(
            predicates=predicates,
            dialect=sqlglot_dialect,
        )

        # 9. SELECT 顺序固定为：维度列在前、指标聚合列在后。
        #    这让生成结果更稳定，也让 Evidence 与测试更容易比较。
        select_expressions: list[exp.Expression] = []
        for column_name in dimension_columns:
            select_expressions.append(exp.column(column_name))
        select_expressions.extend(metric_selects)

        # 10. FROM 使用 SQLGlot Table AST。
        #     table.full_name 可以包含库/模式前缀，exp.to_table 会按标识符结构处理。
        query = exp.select(*select_expressions).from_(
            exp.to_table(table.full_name)
        )

        # 11. 当前只允许 AND 组合。
        #     注意：不支持 OR 的核心原因是“Phase 4.1 要保持安全、简单、可证明的子集”，
        #     不是因为 OR 天生不安全；复杂布尔逻辑后续应在 Contract 扩展后再支持。
        if predicates:
            condition = predicates[0]
            for predicate in predicates[1:]:
                condition = exp.and_(condition, predicate)
            query = query.where(condition)

        # 12. GROUP BY 再次从 SchemaBinding 解析，而不是直接复用逻辑名称。
        #     这样最终 SQL 只出现已经确认过的物理列。
        group_by_columns = self._resolve_group_by_columns(
            plan=plan,
            linked_schema=linked_schema,
            table=table,
        )
        if group_by_columns is None:
            return self._fallback(
                CompilationFallbackReason.UNRESOLVED_SCHEMA,
                "Group-by physical binding is unavailable.",
            )

        if group_by_columns:
            query = query.group_by(
                *(exp.column(column_name) for column_name in group_by_columns)
            )

        # 13. AST 渲染使用 SQLGlot dialect；对外 GeneratedSQL 仍保留产品 dialect。
        sql = query.sql(dialect=sqlglot_dialect)

        # Evidence 保存已生成谓词的最终渲染结果，方便 Evaluation、日志和未来 Artifact 层消费。
        filter_expressions = tuple(
            predicate.sql(dialect=sqlglot_dialect)
            for predicate in predicates
        )

        evidence = CompilationEvidence(
            metric_names=tuple(metric.name for metric in metrics),
            physical_table=table.full_name,
            metric_expressions=metric_expressions,
            dimension_columns=dimension_columns,
            filter_expressions=filter_expressions,
            group_by_columns=group_by_columns,
        )

        return MetricCompilationOutcome.compiled(
            generated_sql=GeneratedSQL(
                sql=sql,
                dialect=dialect,
            ),
            evidence=evidence,
        )

    # ========================================================
    # Metrics
    # ========================================================

    def _compile_metrics(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        table: TableMetadata,
        dialect: str,
    ) -> tuple[
        list[exp.Expression],
        tuple[str, ...],
        tuple[SemanticMetric, ...],
        MetricCompilationOutcome | None,
    ]:
        """
        把 QueryPlan 中的每个逻辑指标编译成聚合 SELECT AST。

        返回四部分：
        1. `selects`：真正进入 SELECT 的 AST（已经加指标别名）；
        2. `rendered`：不带别名的聚合表达式文本，进入 CompilationEvidence；
        3. `metrics`：已确认的 SemanticMetric，供后续读取 fixed_filters；
        4. `metric_error`：若任一指标超出 V1 能力，直接返回统一 fallback Outcome。

        这里采用“全有或全无”：多个指标中只要有一个不能确定性编译，整个查询都回退 LLM。
        不允许一半 Compiler、一半 LLM 再拼接，否则会重新引入混合语义与审计困难。
        """
        selects: list[exp.Expression] = []
        rendered: list[str] = []
        metrics: list[SemanticMetric] = []

        for metric_name in plan.metrics:
            # A. 指标必须来自当前批准的 SemanticModel；Compiler 不自行创造指标定义。
            metric = self._semantic_model.get_metric(metric_name)
            if metric is None:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason.UNRESOLVED_SCHEMA,
                        f"Metric is unavailable in SemanticModel: {metric_name}",
                    ),
                )

            # B. V1 只编译 aggregation + source_column 能完整表达的简单指标。
            #    expression-only 指标（如加权利率）仍交给 LLM Generator。
            if metric.aggregation is None or metric.source_column is None:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason.COMPLEX_EXPRESSION,
                        f"Metric requires expression-level generation: {metric.name}",
                    ),
                )

            aggregation = metric.aggregation.strip().lower()
            if aggregation not in self._SUPPORTED_AGGREGATIONS:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason.UNSUPPORTED_AGGREGATION,
                        f"Unsupported metric aggregation: {aggregation}",
                    ),
                )

            # C. SemanticMetric 存在还不够；SchemaLinker 必须对本次任务正式确认 METRIC binding。
            binding = linked_schema.get_binding(
                kind=SchemaBindingKind.METRIC,
                logical_name=metric.name,
            )
            if binding is None:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason.UNRESOLVED_SCHEMA,
                        f"Metric has no SchemaBinding: {metric.name}",
                    ),
                )

            # D. 当前所有指标必须落在本次唯一物理表上。
            if not self._table_matches(
                binding.physical_table,
                table.full_name,
            ):
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason.MULTI_TABLE,
                        "Metrics resolve to different physical tables.",
                    ),
                )

            source_column = metric.source_column.strip()

            # E. 物理元数据必须真的包含 source_column。
            if table.get_column(source_column) is None:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason.UNRESOLVED_SCHEMA,
                        "Metric source column is unavailable in LinkedSchema.",
                    ),
                )

            # F. 再确认该 source_column 确实包含在本次 metric binding 的物理列集合中。
            #    这与上面的元数据存在性校验是不同层次：
            #    元数据回答“表里有没有”，Binding 回答“本次逻辑指标是不是绑定到它”。
            binding_columns = {
                column.strip().lower()
                for column in binding.physical_columns
            }
            if source_column.lower() not in binding_columns:
                return (
                    [],
                    (),
                    (),
                    self._fallback(
                        CompilationFallbackReason.UNRESOLVED_SCHEMA,
                        "Metric source column was not confirmed by SchemaBinding.",
                    ),
                )

            # G. 至此指标已经通过所有确定性前置校验，可以构建聚合 AST。
            aggregate_expression = self._build_aggregate(
                aggregation=aggregation,
                source_column=source_column,
            )

            # 指标名作为 SELECT 别名，使 SQL 输出与逻辑指标 Contract 保持对应。
            aliased_expression = exp.alias_(
                aggregate_expression,
                metric.name,
                quoted=False,
            )

            selects.append(aliased_expression)
            rendered.append(
                aggregate_expression.sql(dialect=dialect)
            )
            metrics.append(metric)

        return (
            selects,
            tuple(rendered),
            tuple(metrics),
            None,
        )

    @staticmethod
    def _build_aggregate(
        *,
        aggregation: str,
        source_column: str,
    ) -> exp.Expression:
        """
        根据已验证的聚合类型构建 SQLGlot 聚合 AST。

        调用方在进入本方法前已经通过 `_SUPPORTED_AGGREGATIONS` 白名单校验，
        因此末尾的 ValueError 属于“内部编程 Contract 被破坏”的保护，而不是正常 fallback 分支。
        """
        column = exp.column(source_column)

        if aggregation == "sum":
            return exp.Sum(this=column)
        if aggregation == "avg":
            return exp.Avg(this=column)
        if aggregation == "min":
            return exp.Min(this=column)
        if aggregation == "max":
            return exp.Max(this=column)
        if aggregation == "count":
            return exp.Count(this=column)
        if aggregation == "count_distinct":
            # SQLGlot 中 COUNT(DISTINCT col) 表达为 Count(Distinct(expressions=[col]))。
            return exp.Count(
                this=exp.Distinct(
                    expressions=[column]
                )
            )

        raise ValueError(
            f"Unsupported aggregation {aggregation!r}."
        )

    # ========================================================
    # Dimensions / Grouping
    # ========================================================

    @staticmethod
    def _validate_grouping(
        plan: QueryPlan,
    ) -> bool:
        """
        判断当前 QueryPlan 是否满足 V1 的严格 grouping Contract。

        注意，这不是在实现完整 SQL GROUP BY 语义检查，而是在主动收窄 Compiler 的能力边界：
        QueryPlan.dimensions 与 QueryPlan.group_by 必须集合完全一致。
        任何“选择维度但不分组”或“额外分组但不输出维度”的情况都回退 LLM。
        """
        dimensions = {
            value.strip().lower()
            for value in plan.dimensions
        }
        group_by = {
            value.strip().lower()
            for value in plan.group_by
        }
        return dimensions == group_by

    def _resolve_dimension_columns(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        table: TableMetadata,
    ) -> tuple[str, ...] | None:
        """把 QueryPlan.dimensions 解析成唯一物理列集合。"""
        return self._resolve_columns(
            logical_names=plan.dimensions,
            linked_schema=linked_schema,
            table=table,
        )

    def _resolve_group_by_columns(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        table: TableMetadata,
    ) -> tuple[str, ...] | None:
        """把 QueryPlan.group_by 解析成唯一物理列集合。"""
        return self._resolve_columns(
            logical_names=plan.group_by,
            linked_schema=linked_schema,
            table=table,
        )

    @staticmethod
    def _resolve_columns(
        *,
        logical_names: tuple[str, ...],
        linked_schema: LinkedSchema,
        table: TableMetadata,
    ) -> tuple[str, ...] | None:
        """
        将逻辑维度名转换为本次查询允许使用的物理列名。

        每个逻辑名必须同时满足：
        1. 存在 COLUMN 类型 SchemaBinding；
        2. 恰好绑定一个物理列；
        3. 绑定表与当前唯一物理表匹配；
        4. 当前 TableMetadata 中确实存在该列。

        任一条件失败都返回 None，由上层转换为 UNRESOLVED_SCHEMA fallback。
        """
        result: list[str] = []

        for logical_name in logical_names:
            binding = linked_schema.get_binding(
                kind=SchemaBindingKind.COLUMN,
                logical_name=logical_name,
            )
            if binding is None:
                return None

            # V1 不处理一个逻辑维度映射多个物理列，因为无法确定最终 SELECT/GROUP BY 结构。
            if len(binding.physical_columns) != 1:
                return None

            if not MetricSQLCompiler._table_matches(
                binding.physical_table,
                table.full_name,
            ):
                return None

            physical_column = binding.physical_columns[0]
            if table.get_column(physical_column) is None:
                return None

            result.append(physical_column)

        return tuple(result)

    # ========================================================
    # Planner Filter Parser / Safe Subset Validator
    # ========================================================

    def _parse_plan_filter(
        self,
        *,
        filter_text: str,
        dialect: str,
        table: TableMetadata,
    ) -> exp.Expression | None:
        """
        将 QueryPlan 中的过滤字符串转换为经过白名单验证的谓词 AST。

        当前 QueryPlan.filters 还是字符串，因此这里是 Compiler 的关键边界：
        不能把字符串直接拼进最终 SQL。处理顺序必须是：

            filter text
                ↓
            SQLGlot parse
                ↓
            只允许单条 SELECT wrapper
                ↓
            提取 WHERE predicate AST
                ↓
            `_validate_predicate` 递归白名单验证
                ↓
            copy 后返回给最终 SQL Builder

        `SELECT 1 WHERE ...` 只是为了让 SQLGlot 在合法 SQL 上下文中解析“谓词片段”；
        真正的安全边界是后续“单 statement + AST 白名单 + 物理列存在性”三层校验，
        不能把安全性错误归因于 wrapper 本身。
        """
        normalized = filter_text.strip()
        if not normalized:
            return None

        try:
            statements = parse(
                f"SELECT 1 WHERE {normalized}",
                read=dialect,
            )
        except ParseError:
            return None

        # 多语句输入不属于过滤谓词 Contract，例如 `a=1; DROP ...` 会在这里被拒绝。
        if len(statements) != 1:
            return None

        statement = statements[0]
        if not isinstance(statement, exp.Select):
            return None

        where = statement.args.get("where")
        if not isinstance(where, exp.Where):
            return None

        predicate = where.this

        if not self._validate_predicate(
            predicate=predicate,
            table=table,
        ):
            return None

        # SQLGlot AST 是可变对象。返回 copy，避免后续 Builder 修改节点时影响解析树中的原节点。
        return predicate.copy()

    def _validate_predicate(
        self,
        *,
        predicate: exp.Expression,
        table: TableMetadata,
    ) -> bool:
        """
        递归验证 Planner filter 是否完全落在 Phase 4.1 的安全、确定性子集中。

        允许：
        - 括号；
        - AND；
        - = / != / > / >= / < / <=；
        - IN(literal, ...)，不允许子查询；
        - BETWEEN literal AND literal。

        对普通比较，左侧必须是当前物理表中的列，右侧必须是 literal。
        因此诸如 `a = b`、`a + 1 > 2`、`func(a) = 1`、`EXISTS(...)` 等都不会进入 Compiler。

        不支持 OR 并不是宣称 OR 本身不安全，而是 V1 尚未把复杂布尔逻辑纳入可证明的编译子集。
        """
        if isinstance(predicate, exp.Paren):
            return self._validate_predicate(
                predicate=predicate.this,
                table=table,
            )

        if isinstance(predicate, exp.And):
            return (
                self._validate_predicate(
                    predicate=predicate.this,
                    table=table,
                )
                and self._validate_predicate(
                    predicate=predicate.expression,
                    table=table,
                )
            )

        if isinstance(
            predicate,
            (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE),
        ):
            return (
                self._valid_column(predicate.this, table)
                and self._is_literal(predicate.expression)
            )

        if isinstance(predicate, exp.In):
            if not self._valid_column(predicate.this, table):
                return False

            # IN (SELECT ...) 会保存在 query 参数中，必须显式拒绝。
            if predicate.args.get("query") is not None:
                return False

            values = tuple(predicate.expressions)
            return bool(values) and all(
                self._is_literal(value)
                for value in values
            )

        if isinstance(predicate, exp.Between):
            return (
                self._valid_column(predicate.this, table)
                and self._is_literal(predicate.args.get("low"))
                and self._is_literal(predicate.args.get("high"))
            )

        return False

    @staticmethod
    def _is_literal(value) -> bool:
        """
        判断谓词值是否属于 V1 允许的常量节点。

        SQLGlot 的字符串/数字使用 Literal，布尔值使用 Boolean。
        NULL、日期函数、Cast、Identifier、Column 等当前都不进入这一确定性子集。
        """
        return isinstance(
            value,
            (exp.Literal, exp.Boolean),
        )

    @staticmethod
    def _valid_column(
        expression,
        table: TableMetadata,
    ) -> bool:
        """
        验证谓词左侧是否是当前唯一物理表中真实存在的列。

        无表限定符时，在“单表 Compiler”前提下可直接接受；
        有限定符时，仅允许当前 full_name 或裸表名。
        """
        if not isinstance(expression, exp.Column):
            return False

        if table.get_column(expression.name) is None:
            return False

        qualifier = expression.table
        if not qualifier:
            return True

        normalized = qualifier.strip().lower()
        full_name = table.full_name.strip().lower()
        bare_name = full_name.split(".")[-1]

        return normalized in {full_name, bare_name}

    # ========================================================
    # Semantic Fixed Filter Builder
    # ========================================================

    def _build_semantic_filter(
        self,
        *,
        semantic_filter: SemanticFilter,
        table: TableMetadata,
    ) -> exp.Expression | None:
        """
        把结构化 SemanticFilter 转成 SQLGlot 谓词 AST。

        与 Planner filter 不同，这里的输入已经是结构化字段：column / operator / value。
        但“结构化”不等于“无条件可信”，仍然必须验证：
        - 列真实存在；
        - operator 属于 Compiler 白名单；
        - value 能被转换为允许的 literal 结构。
        """
        column_name = semantic_filter.column.strip()
        if table.get_column(column_name) is None:
            return None

        # 将资产层可能出现的操作符别名归一成内部名称，后续只处理固定集合。
        operator = semantic_filter.operator.strip().lower()
        operator = {
            "=": "eq",
            "==": "eq",
            "eq": "eq",
            "!=": "neq",
            "<>": "neq",
            "neq": "neq",
            ">": "gt",
            "gt": "gt",
            ">=": "gte",
            "gte": "gte",
            "<": "lt",
            "lt": "lt",
            "<=": "lte",
            "lte": "lte",
            "in": "in",
            "between": "between",
        }.get(operator)

        if operator is None:
            return None

        column = exp.column(column_name)
        value = semantic_filter.value

        if operator == "in":
            # 当前 SemanticFilter Contract 用 tuple 表示多个 IN 值；非 tuple 按单值处理。
            values = value if isinstance(value, tuple) else (value,)
            expressions: list[exp.Expression] = []

            for item in values:
                literal = self._literal(item)
                if literal is None:
                    return None
                expressions.append(literal)

            if not expressions:
                return None

            return exp.In(
                this=column,
                expressions=expressions,
            )

        if operator == "between":
            # BETWEEN 必须精确提供两个边界，禁止 Compiler 猜缺失边界。
            if not isinstance(value, tuple) or len(value) != 2:
                return None

            low = self._literal(value[0])
            high = self._literal(value[1])
            if low is None or high is None:
                return None

            return exp.Between(
                this=column,
                low=low,
                high=high,
            )

        literal = self._literal(value)
        if literal is None:
            return None

        builders = {
            "eq": exp.EQ,
            "neq": exp.NEQ,
            "gt": exp.GT,
            "gte": exp.GTE,
            "lt": exp.LT,
            "lte": exp.LTE,
        }
        builder = builders.get(operator)
        if builder is None:
            return None

        return builder(
            this=column,
            expression=literal,
        )

    @staticmethod
    def _literal(value) -> exp.Expression | None:
        """
        把 SemanticFilter.value 的 Python 标量转换成 SQLGlot literal。

        当前只批准 bool / int / float / str。
        `None` 没有被自动翻译为 IS NULL，因为 `=` 与 `IS NULL` 语义不同，
        在 Contract 未显式支持前不能由 Compiler 擅自改写。
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return exp.Boolean(this=value)
        if isinstance(value, (int, float)):
            return exp.Literal.number(str(value))
        if isinstance(value, str):
            return exp.Literal.string(value)
        return None

    # ========================================================
    # Utilities
    # ========================================================

    @staticmethod
    def _dedupe_predicates(
        *,
        predicates: list[exp.Expression],
        dialect: str,
    ) -> list[exp.Expression]:
        """
        对已经通过安全校验的谓词做轻量文本归一化去重。

        这里不是通用 SQL 等价性判断器，只消除渲染后“大小写/空格差异”的完全重复条件。
        例如逻辑等价但写法不同的 `a BETWEEN 1 AND 2` 与 `a >= 1 AND a <= 2`
        不会被认为重复，这是有意保持的简单边界。
        """
        result: list[exp.Expression] = []
        seen: set[str] = set()

        for predicate in predicates:
            key = (
                predicate.sql(dialect=dialect)
                .lower()
                .replace(" ", "")
            )
            if key in seen:
                continue

            seen.add(key)
            result.append(predicate)

        return result

    @staticmethod
    def _table_matches(
        left: str,
        right: str,
    ) -> bool:
        """
        比较两个物理表标识是否可以视为同一张表。

        优先完整名称匹配；为兼容当前 SchemaBinding 中可能只保存裸表名的情况，
        V1 还允许 `db.schema.table` 与 `table` 的裸名匹配。

        这不是跨 schema 的全局唯一性保证：如果未来一个查询上下文允许多个 schema 中存在同名表，
        这里必须随 Certified Join / 更严格物理标识 Contract 一起收紧，而不能继续依赖裸名。
        """
        normalized_left = left.strip().lower()
        normalized_right = right.strip().lower()

        if normalized_left == normalized_right:
            return True

        return (
            normalized_left.split(".")[-1]
            == normalized_right.split(".")[-1]
        )

    @staticmethod
    def _fallback(
        reason: CompilationFallbackReason,
        detail: str,
    ) -> MetricCompilationOutcome:
        """
        统一构造“当前请求不适合确定性编译”的结果。

        fallback 是 Generation 路由信息，不是业务失败：
        Runtime 收到 NOT_COMPILABLE 后会继续调用 SQLGenerator(LLM)。
        只有最终 LLM/Trust/Semantic Validation 失败时，整个 Text-to-SQL 才可能失败。
        """
        return MetricCompilationOutcome.fallback(
            fallback_reason=reason,
            reason=detail,
        )
