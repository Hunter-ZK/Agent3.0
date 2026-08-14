from __future__ import annotations

from sql_pilot_engine.context.builder import (
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
from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)
from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLRequest,
    TextToSQLResult,
)
from sql_pilot_engine.workflow.sql_agent_workflow import (
    SQLAgentWorkflow,
)


class TextToSQLService:

    def __init__(
        self,
        *,
        semantic_model: SemanticModel,
        knowledge_retriever: KnowledgeRetriever,
        verified_sql_retriever: VerifiedSQLRetriever,
        context_builder: QueryContextBuilder,
        planner: QueryPlanner,
        sql_generator: SQLGenerator,
        validation_workflow: SQLAgentWorkflow,
    ) -> None:

        self.semantic_model = semantic_model

        self.knowledge_retriever = (
            knowledge_retriever
        )

        self.verified_sql_retriever = (
            verified_sql_retriever
        )

        self.context_builder = context_builder

        self.planner = planner

        self.sql_generator = sql_generator

        self.validation_workflow = (
            validation_workflow
        )

        self.semantic_renderer = (
            SemanticModelRenderer()
        )
        
    def generate(
        self,
        request: TextToSQLRequest,
    ) -> TextToSQLResult:
        
        question = request.question
        
        business_knowledge = (
            self.knowledge_retriever.retrieve(
                question=question,
                top_k=5,
            )
        )
        
        verified_sql = (
            self.verified_sql_retriever.retrieve(
                question=question,
                top_k=3,
            )
        )
        
        query_context = (
            self.context_builder.build(
                question=question,
                business_knowledge=business_knowledge,
                verified_sql=verified_sql,
            )
        )
        
        semantic_context = (
            self.semantic_renderer.render(
                self.semantic_model
            )
        )
        
        query_plan = self.planner.plan(
            question=question,
            semantic_context=semantic_context,
            query_context=query_context,
        )
        
        generated = (
            self.sql_generator.generate(
                question=question,
                plan=query_plan,
                semantic_context=semantic_context,
                query_context=query_context,
                dialect=request.dialect,
            )
        )
        
        validation = (
            self.validation_workflow.run(
                generated.sql,
                dialect=request.dialect,
            )
        )
        
        trusted_sql = (
            self._resolve_trusted_sql(
                generated_sql=generated.sql,
                validation=validation,
            )
        )
        
        return TextToSQLResult(
            question=question,
            query_plan=query_plan,
            generated_sql=generated.sql,
            trusted_sql=trusted_sql,
            success=validation.success,
            validation_status=(
                validation.final_status
            ),
        )