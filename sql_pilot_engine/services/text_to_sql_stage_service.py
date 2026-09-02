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

from sql_pilot_engine.generation.models import (
    GeneratedSQL,
    QueryPlan,
    QueryPlanningOutcome,
    GenerationSource,
    MetricCompilationOutcome,
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

from sql_pilot_engine.core.trust_evidence import (
    SQLTrustEvidence,
)

from sql_pilot_engine.generation.metric_compiler import (
    MetricSQLCompiler,
)

class TextToSQLStageService:
    """
    Text-to-SQL 各业务 Stage 的应用层执行服务。

    职责：

    Context Intelligence
        ↓
    Planning
        ↓
    Schema Linking
        ↓
    SQL Generation
        ↓
    Trusted SQL
        ↓
    Semantic Validation

    注意：

    本 Service 不负责：

    - LangGraph State
    - Edge / Routing
    - Retry Routing
    - interrupt / resume
    - thread_id / turn_id
    - Checkpoint
    - HITL 生命周期
    - 创建任何外部依赖

    上述职责仍属于 Runtime / Composition Root。
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
        trusted_sql_workflow: (
            TrustedSQLWorkflowPort
        ),
        semantic_validator: (
            SemanticSQLValidator | None
        ) = None,
        knowledge_top_k: int = 5,
        verified_sql_top_k: int = 3,
    ) -> None:

        if knowledge_top_k <= 0:
            raise ValueError(
                "knowledge_top_k "
                "must be greater than 0"
            )

        if verified_sql_top_k <= 0:
            raise ValueError(
                "verified_sql_top_k "
                "must be greater than 0"
            )

        self._semantic_model = (
            semantic_model
        )

        self._semantic_renderer = (
            SemanticModelRenderer()
        )

        self._knowledge_retriever = (
            knowledge_retriever
        )

        self._verified_sql_retriever = (
            verified_sql_retriever
        )

        self._context_builder = (
            context_builder
        )

        self._planner = planner

        self._schema_linker = (
            schema_linker
        )
        
        self._metric_compiler = (
            metric_compiler
        )

        self._sql_generator = (
            sql_generator
        )

        self._trusted_sql_workflow = (
            trusted_sql_workflow
        )

        self._semantic_validator = (
            semantic_validator
        )

        self._knowledge_top_k = (
            knowledge_top_k
        )

        self._verified_sql_top_k = (
            verified_sql_top_k
        )

    # ========================================================
    # Context Intelligence
    # ========================================================

    def build_query_context(
        self,
        *,
        question: str,
        session_context: tuple[
            str,
            ...
        ] = (),
    ) -> QueryContext:

        semantic_context = (
            self._semantic_renderer
            .render(
                self._semantic_model
            )
        )

        business_knowledge = (
            self._knowledge_retriever
            .retrieve(
                question=question,
                top_k=(
                    self._knowledge_top_k
                ),
            )
        )

        verified_sql = (
            self._verified_sql_retriever
            .retrieve(
                question=question,
                top_k=(
                    self._verified_sql_top_k
                ),
            )
        )

        return self._context_builder.build(
            question=question,

            semantic_context=(
                semantic_context
            ),

            business_knowledge=(
                business_knowledge
            ),

            verified_sql=(
                verified_sql
            ),

            session_context=(
                session_context
            ),
        )

    # ========================================================
    # Planning
    # ========================================================

    def plan(
        self,
        *,
        query_context: QueryContext,
    ) -> QueryPlanningOutcome:

        return self._planner.plan(
            query_context=(
                query_context
            )
        )

    # ========================================================
    # Schema Linking
    # ========================================================

    def link_schema(
        self,
        *,
        plan: QueryPlan,
    ) -> LinkedSchema:

        return self._schema_linker.link(
            plan=plan
        )

    # ========================================================
    # SQL Compile
    # ========================================================

    def try_compile_sql(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        dialect: str,
    ) -> MetricCompilationOutcome:

        return (
            self._metric_compiler
            .compile(
                plan=plan,

                linked_schema=(
                    linked_schema
                ),

                dialect=dialect,
            )
        )

    # ========================================================
    # SQL Generation
    # ========================================================

    def generate_sql(
        self,
        *,
        plan: QueryPlan,
        linked_schema: LinkedSchema,
        query_context: QueryContext,
        dialect: str,
        revision_feedback: tuple[
            str,
            ...
        ] = (),
    ) -> GeneratedSQL:

        return self._sql_generator.generate(
            plan=plan,

            linked_schema=(
                linked_schema
            ),

            query_context=(
                query_context
            ),

            dialect=dialect,

            revision_feedback=(
                revision_feedback
            ),
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
        
        trust_evidence = (
            SQLTrustEvidence(
                query_plan=plan,
                linked_schema=linked_schema,
                semantic_model=self._semantic_model,
            )
        )

        return (
            self._trusted_sql_workflow
            .run(
                generated_sql,

                dialect=dialect,

                query_context=(
                    query_context
                ),
                
                trust_evidence=trust_evidence,

                rule_packs=("text_to_sql",),
                
                enable_llm = (
                    False
                    if (generation_source is GenerationSource.COMPILED)
                    else None
                )
            )
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
    ) -> (
        SemanticValidationResult | None
    ):

        if (
            self._semantic_validator
            is None
        ):
            return None

        return (
            self._semantic_validator
            .validate(
                sql=sql,

                plan=plan,

                query_context=(
                    query_context
                ),
            )
        )