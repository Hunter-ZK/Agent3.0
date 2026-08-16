from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger(__name__)

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
    SQLAgentWorkflow, SQLAgentWorkflowResult
)
from sql_pilot_engine.observability.context import (
    bind_run_id
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

        run_id = uuid.uuid4().hex[:8]

        with bind_run_id(run_id):
            total_start = time.perf_counter()


            logger.info(
                "text_to_sql.start question_chars=%d",
                len(request.question),
            )
            try:
                logger.info(
                    "context.start"
                )

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

                stage_start = time.perf_counter()

                query_context = (
                    self.context_builder.build(
                        question=question,
                        business_knowledge=business_knowledge,
                        verified_sql=verified_sql,
                    )
                )

                elapsed_ms = int(
                    (time.perf_counter() - stage_start) * 1000
                )

                logger.info(
                    "context.end "
                    "knowledge_docs=%d "
                    "verified_sql_docs=%d "
                    "elapsed_ms=%d",
                    len(business_knowledge),
                    len(verified_sql),
                    elapsed_ms,
                )
                
                semantic_context = (
                    self.semantic_renderer.render(
                        self.semantic_model
                    )
                )

                stage_start = time.perf_counter()

                logger.info(
                    "planner.start"
                )
                
                query_plan = self.planner.plan(
                    question=question,
                    semantic_context=semantic_context,
                    query_context=query_context,
                )

                elapsed_ms = int(
                    (
                        time.perf_counter()
                        - stage_start
                    )
                    * 1000
                )

                logger.info(
                    "planner.end "
                    "tables=%d "
                    "dimensions=%d "
                    "metrics=%d "
                    "elapsed_ms=%d",
                    len(query_plan.tables),
                    len(query_plan.dimensions),
                    len(query_plan.metrics),
                    elapsed_ms,
                )

                stage_start = time.perf_counter()

                logger.info(
                    "generator.start"
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

                elapsed_ms = int(
                    (
                        time.perf_counter()
                        - stage_start
                    )
                    * 1000
                )

                logger.info(
                    "generator.end "
                    "sql_chars=%d "
                    "elapsed_ms=%d",
                    len(generated.sql),
                    elapsed_ms,
                )

                stage_start = time.perf_counter()

                logger.info(
                    "validation.start"
                )
                
                validation = (
                    self.validation_workflow.run(
                        generated.sql,
                    )
                )

                elapsed_ms = int(
                    (
                        time.perf_counter()
                        - stage_start
                    )
                    * 1000
                )

                logger.info(
                    "validation.end "
                    "status=%s "
                    "elapsed_ms=%d",
                    validation,
                    elapsed_ms,
                )
                
                trusted_sql = (
                    self._resolve_trusted_sql(
                        generated_sql=generated.sql,
                        validation=validation,
                    )
                )

                result = TextToSQLResult(
                    question=question,
                    query_plan=query_plan,
                    generated_sql=generated.sql,
                    trusted_sql=trusted_sql,
                    success=validation.success,
                    validation_status=(
                        validation.final_status
                    ),
                )

            except Exception:

                elapsed_ms = int(
                    (time.perf_counter() - total_start) * 1000
                )

                logger.exception(
                    "text_to_sql.error elapsed_ms=%d",
                    elapsed_ms,
                )

                raise
                

            logger.info(
                "run=%s text_to_sql.end success=%s "
                "validation_status=%s elapsed_ms=%d",
                run_id,
                result.success,
                result.validation_status,
                elapsed_ms,
            )
        
        return result
        
    
    @staticmethod
    def _resolve_trusted_sql(
        *,
        generated_sql: str,
        validation: SQLAgentWorkflowResult,
    ) -> str | None:
        
        if not validation.success:
            return None
        
        if (
            validation.fix_response is not None and validation.fix_response.fixed_sql
        ):
            return (
                validation.fix_response.fixed_sql
            )
            
        return generated_sql