from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
    QueryContextBuilder,
)
from sql_pilot_engine.context.retriever import (
    KnowledgeRetriever,
    VerifiedSQLRetriever,
)
from sql_pilot_engine.context.semantic.models import (
    SemanticModel,
)
from sql_pilot_engine.context.semantic.renderer import (
    SemanticModelRenderer,
)
from sql_pilot_engine.core.trust_evidence import (
    SQLTrustEvidence,
)
from sql_pilot_engine.generation.metric_compiler import (
    MetricSQLCompiler,
)
from sql_pilot_engine.generation.models import (
    GeneratedSQL,
    GenerationSource,
    MetricCompilationOutcome,
    QueryPlan,
    QueryPlanningOutcome,
)
from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)
from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)
from sql_pilot_engine.linking.models import (
    LinkedSchema,
)
from sql_pilot_engine.linking.schema_linker import (
    SchemaLinker,
)
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticSQLValidator,
    SemanticValidationResult,
)
from sql_pilot_engine.workflow.protocols import (
    TrustedSQLWorkflowPort,
    TrustedSQLWorkflowResultView,
)


class TextToSQLStageService:
    """
    Text-to-SQL 各业务 Stage 的应用层执行服务。

    【架构位置】

        QueryRuntimeNodes
            ↓
        TextToSQLStageService              <- 本类
            ↓
        ┌───────────────────────────────────────────────┐
        │ Context Intelligence                         │
        │ Planning                                     │
        │ Schema Linking                               │
        │ Metric Compilation ──fallback──> LLM Generate│
        │ Trusted SQL                                  │
        │ Semantic Validation                          │
        └───────────────────────────────────────────────┘

    为什么需要这一层，而不是让 LangGraph Node 直接 new / 调用所有组件：
    1. Runtime Node 只处理 State、Routing、Retry、HITL；
    2. StageService 负责“一个业务 Stage 怎么调用已有能力”；
    3. Composition Root 负责创建依赖；
    4. 具体算法仍留在 Planner / Linker / Compiler / Generator / Workflow 内。

    这样 Graph 不会重新退化成巨型 Dependency Container，业务能力也可以在非 LangGraph
    场景中复用和单测。

    【本 Service 明确不负责】
    - LangGraph State 的读写；
    - Edge / Routing；
    - Retry / clarification 轮次；
    - interrupt / resume；
    - thread_id / turn_id；
    - Checkpoint；
    - HITL 生命周期；
    - 创建任何外部依赖。

    Phase 4.1 的关键变化是：Generation 不再只有 SQLGenerator 一条路径。Planning + Linking
    完成后先尝试 MetricSQLCompiler；只有 NOT_COMPILABLE 才由 Runtime 路由到 LLM Generator。
    """

    def __init__(
        self,
        *,
        semantic_model: SemanticModel,
        knowledge_retriever: KnowledgeRetriever,
        verified_sql_retriever: VerifiedSQLRetriever,
        context_builder: QueryContextBuilder,
        planner: QueryPlanner,
        schema_linker: SchemaLinker,
        metric_compiler: MetricSQLCompiler,
        sql_generator: SQLGenerator,
        trusted_sql_workflow: TrustedSQLWorkflowPort,
        semantic_validator: SemanticSQLValidator | None = None,
        knowledge_top_k: int = 5,
        verified_sql_top_k: int = 3,
    ) -> None:
        """
        注入 Text-to-SQL 各 Stage 已经组装好的依赖。

        semantic_model 同时会被 SchemaLinker、Metric Compiler、Trust Evidence 使用。
        这里保存同一实例的引用，确保一条请求链消费的是同一份已批准语义资产；
        StageService 不负责加载或修改 SemanticModel。
        """

        if knowledge_top_k <= 0:
            raise ValueError(
                "knowledge_top_k must be greater than 0"
            )

        if verified_sql_top_k <= 0:
            raise ValueError(
                "verified_sql_top_k must be greater than 0"
            )

        self._semantic_model = semantic_model
        self._semantic_renderer = SemanticModelRenderer()
        self._knowledge_retriever = knowledge_retriever
        self._verified_sql_retriever = verified_sql_retriever
        self._context_builder = context_builder
        self._planner = planner
        self._schema_linker = schema_linker
        self._metric_compiler = metric_compiler
        self._sql_generator = sql_generator
        self._trusted_sql_workflow = trusted_sql_workflow
        self._semantic_validator = semantic_validator
        self._knowledge_top_k = knowledge_top_k
        self._verified_sql_top_k = verified_sql_top_k

    # ========================================================
    # Context Intelligence
    # ========================================================

    def build_query_context(
        self,
        *,
        question: str,
        session_context: tuple[str, ...] = (),
    ) -> QueryContext:
        """
        构造“本轮任务上下文快照”。

        这里把长期资产/检索结果转为单次任务可消费的 QueryContext：
        - SemanticModel -> renderer -> semantic_context；
        - business knowledge -> KnowledgeRetriever；
        - verified SQL -> VerifiedSQLRetriever；
        - session context -> 调用方传入。

        QueryContext 不是 SemanticModel 本体；后续 Planner/Generator 读取的是任务上下文，
        Trust Evidence 则仍可携带结构化 SemanticModel。两者不能混成一个对象。
        """

        semantic_context = self._semantic_renderer.render(
            self._semantic_model
        )

        business_knowledge = self._knowledge_retriever.retrieve(
            question=question,
            top_k=self._knowledge_top_k,
        )

        verified_sql = self._verified_sql_retriever.retrieve(
            question=question,
            top_k=self._verified_sql_top_k,
        )

        return self._context_builder.build(
            question=question,
            semantic_context=semantic_context,
            business_knowledge=business_knowledge,
            verified_sql=verified_sql,
            session_context=session_context,
        )

    # ========================================================
    # Planning
    # ========================================================

    def plan(
        self,
        *,
        query_context: QueryContext,
    ) -> QueryPlanningOutcome:
        """
        调用 QueryPlanner 形成 QueryPlan 或 PlanningClarification。

        StageService 不在这里二次解释 Planner 结果；澄清分支由 Runtime Node 根据返回类型路由。
        """

        return self._planner.plan(
            query_context=query_context
        )

    # ========================================================
    # Schema Linking
    # ========================================================

    def link_schema(
        self,
        *,
        plan: QueryPlan,
    ) -> LinkedSchema:
        """
        把 QueryPlan 中的逻辑对象解析为物理表/列绑定。

        Metric Compiler 与 SQLGenerator 都必须消费 LinkedSchema，不能自己绕过 Linker 猜字段。
        """

        return self._schema_linker.link(
            plan=plan
        )

    # ========================================================
    # Deterministic Metric Compilation
    # ========================================================

    def try_compile_sql(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        dialect: str,
    ) -> MetricCompilationOutcome:
        """
        在进入 LLM SQLGenerator 之前尝试确定性 Metric Compilation。

        【为什么叫 try_compile_sql】
        NOT_COMPILABLE 是预期业务分支，而不是异常。因此这个方法只把 Compiler 的稳定
        Outcome 原样返回给 Runtime，由 Graph 根据 status 决定：
        - COMPILED -> 直接进入 Trust；
        - NOT_COMPILABLE -> 进入 LLM Generator。

        Service 不负责 fallback routing，否则 Graph 拓扑会被隐藏进业务服务。
        """

        return self._metric_compiler.compile(
            plan=plan,
            linked_schema=linked_schema,
            dialect=dialect,
        )

    # ========================================================
    # LLM SQL Generation
    # ========================================================

    def generate_sql(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        query_context: QueryContext,
        dialect: str,
        revision_feedback: tuple[str, ...] = (),
    ) -> GeneratedSQL:
        """
        调用通用 SQLGenerator 生成 SQL Candidate。

        这个入口同时服务两类情况：
        1. Metric Compiler 因能力边界正常 fallback；
        2. Compiler SQL 通过 Trust 后，Semantic Validation 发现语义不满足，需要 LLM 修订。

        revision_feedback 只用于后者。Compiler 不消费该反馈，因为同样输入重新编译只会得到
        同样的确定性 SQL，Semantic Retry 必须直接走 LLM Generator。
        """

        return self._sql_generator.generate(
            plan=plan,
            linked_schema=linked_schema,
            query_context=query_context,
            dialect=dialect,
            revision_feedback=revision_feedback,
        )

    # ========================================================
    # Trusted SQL
    # ========================================================

    def trust_sql(
        self,
        *,
        generated_sql: str,
        dialect: str,
        query_context: QueryContext,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        generation_source: GenerationSource,
    ) -> TrustedSQLWorkflowResultView:
        """
        把任意 Generation Source 产生的 SQL Candidate 送入统一 Trusted SQL Workflow。

        【核心不变量】
        Compiler 产出的 SQL 只是“确定性生成”，不是天然 Trusted SQL。因此仍必须携带：
        - QueryPlan；
        - LinkedSchema；
        - SemanticModel；
        组成 SQLTrustEvidence，并经过 ``text_to_sql`` rule pack。

        【为什么 compiled 路径关闭 LLM】
        Compiler 已经从结构化事实直接生成 AST。此时再次让 LLM Review 参与初始 Trust，
        会重新引入模型随机性，削弱确定性路径的意义。所以：
        - compiled -> enable_llm=False；
        - llm -> enable_llm=None，保留 TrustedSQLWorkflow 自身的默认配置。

        注意这里没有传 True 给 LLM 路径，因为“默认是否启用 LLM”仍属于 Workflow 配置，
        StageService 只对确定性编译路径做一次明确的策略覆盖。
        """

        trust_evidence = SQLTrustEvidence(
            query_plan=plan,
            linked_schema=linked_schema,
            semantic_model=self._semantic_model,
        )

        return self._trusted_sql_workflow.run(
            generated_sql,
            dialect=dialect,
            query_context=query_context,
            trust_evidence=trust_evidence,
            rule_packs=("text_to_sql",),
            enable_llm=(
                False
                if generation_source is GenerationSource.COMPILED
                else None
            ),
        )

    # ========================================================
    # Semantic Validation
    # ========================================================

    def validate_semantics(
        self,
        *,
        sql: str,
        plan: QueryPlan,
        query_context: QueryContext,
    ) -> SemanticValidationResult | None:
        """
        验证通过 Trust Gate 的 Candidate 是否真正满足 QueryPlan 语义。

        Trust 回答“SQL 是否可信/合规”，Semantic Validation 回答“SQL 是否完成了用户要求”。
        两层不能合并。semantic_validator 为 None 时表示调用方没有启用该可选能力，Runtime
        会按现有策略接受 candidate_sql，而不是在 Service 内自行制造 PASS 结果。
        """

        if self._semantic_validator is None:
            return None

        return self._semantic_validator.validate(
            sql=sql,
            plan=plan,
            query_context=query_context,
        )