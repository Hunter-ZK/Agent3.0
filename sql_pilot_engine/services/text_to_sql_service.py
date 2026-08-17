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
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticSQLValidator,
    SemanticValidationStatus,
    SemanticValidationResult,
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
        semantic_validator: SemanticSQLValidator | None = None,
        max_semantic_retries: int = 1,
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
        
        self.semantic_validator = (
            semantic_validator
        )
        
        if max_semantic_retries < 0:
            raise ValueError(
                "max_semantic_retries "
                "must be >= 0"
            )
        self.max_semantic_retries = (
            max_semantic_retries
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

                stage_start = time.perf_counter()

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
                
                for item in business_knowledge:
                    logger.debug(
                        "context.business_knowledge "
                        "document_id=%s text=%s",
                        item.document.document_id,
                        item.document.text,
                    )
                
                verified_sql = (
                    self.verified_sql_retriever.retrieve(
                        question=question,
                        top_k=3,
                    )
                )
                
                for item in verified_sql:
                    logger.debug(
                        "context.verified_sql "
                        "document_id=%s text=%s",
                        item.document.document_id,
                        item.document.text,
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
                
                logger.debug(
                    "context.semantic\n%s",
                    semantic_context,
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

                revision_feedback: tuple[str, ...] = ()
                
                semantic_result = None
                validation = None
                current_generated_sql = None
                candidate_sql = None
                
                max_attempts = (
                    self.max_semantic_retries + 1
                )
                
                for attempt in range(1, max_attempts + 1,):
                
                    logger.info(
                        "generation_attempt.start "
                        "attempt=%d/%d",
                        attempt,
                        max_attempts,
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
                            revision_feedback=(revision_feedback),
                        )
                    )
                    
                    current_generated_sql = generated.sql

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
                            current_generated_sql
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
                        validation.final_status,
                        elapsed_ms,
                    )
                    

                    candidate_sql = (
                        self._resolve_trusted_sql(
                            generated_sql=current_generated_sql,
                            validation=validation,
                        )
                    )
                    
                    semantic_result = None
                    semantic_passed = True
                    
                    if candidate_sql is None:
                        logger.info(
                            "generation_attempt.end "
                            "attempt=%d "
                            "deterministic_passed=False",
                            attempt,
                        )

                        break
                    
                    if self.semantic_validator is None:
                        break
                        
                    logger.info(
                        "semantic_validation.start"
                    )
                    
                    stage_start = time.perf_counter()
                    
                    semantic_result = (
                        self.semantic_validator.validate(
                            question=question,
                            sql=candidate_sql,
                            plan=query_plan,
                            semantic_context=(
                                semantic_context
                            ),
                            query_context=query_context,
                        )
                    )
                    
                    elapsed_ms = int(
                        (
                            time.perf_counter() - stage_start 
                        ) * 1000
                    )
                    
                    if semantic_result.passed:
                        logger.info(
                            "generation_attempt.end "
                            "attempt=%d "
                            "semantic_status=pass",
                            attempt,
                        )

                        break
                    
                    if (
                        semantic_result.status
                        is SemanticValidationStatus
                        .NEED_CLARIFICATION
                    ):
                        logger.info(
                            "semantic_validation "
                            "need_clarification"
                        )
                        break
                    
                    if attempt >= max_attempts:
                        logger.info(
                            "generation_attempt.end "
                            "attempt=%d "
                            "semantic_status=%s "
                            "retry=False",
                            attempt,
                            semantic_result.status.value,
                        )

                        break
                    
                    revision_feedback = (
                        self._build_revision_feedback(
                            semantic_result
                        )
                    )                   

                    logger.info(
                        "semantic_retry "
                        "attempt=%d "
                        "feedback_items=%d",
                        attempt,
                        len(revision_feedback),
                    )
                    
                logger.info(
                    "semantic_validation.end "
                    "status=%s "
                    "missing=%d "
                    "issues=%d "
                    "elapsed_ms=%d",
                    semantic_result.status.value,
                    len(
                        semantic_result
                        .missing_requirements
                    ),
                    len(
                        semantic_result.issues
                    ),
                    elapsed_ms,
                )
                    
                    
                deterministic_passed = (
                    validation is not None
                    and validation.success
                    and candidate_sql is not None
                )
                    
                    
                semantic_passed = (
                    self.semantic_validator is None 
                    or (
                        semantic_result is not None
                        and semantic_result.passed
                    )
                )

                success = (
                    deterministic_passed
                    and semantic_passed
                )
                
                trusted_sql = (
                    candidate_sql if success else None
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
                    semantic_validation_status=(
                        semantic_result.status.value
                        if semantic_result
                        else None
                    ),

                    semantic_missing_requirements=(
                        semantic_result
                        .missing_requirements
                        if semantic_result
                        else ()
                    ),

                    semantic_issues=(
                        semantic_result.issues
                        if semantic_result
                        else ()
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

            total_elapsed_ms = int(
                (
                    time.perf_counter()
                    - total_start
                )
                * 1000
            )

            logger.info(
                "text_to_sql.end success=%s "
                "validation_status=%s elapsed_ms=%d",
                result.success,
                result.validation_status,
                total_elapsed_ms,
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
    
    
    @staticmethod
    def _build_revision_feedback(
        semantic_result:(SemanticValidationResult),
    ) -> tuple[str, ...]:
        
        feedback: list[str] = []
        
        for requirement in (
            semantic_result
            .missing_requirements
        ):
            feedback.append(
                "Missing requirement: "
                f"{requirement}"
            )

        for issue in semantic_result.issues:
            feedback.append(
                f"Semantic issue: {issue}"
            )

        if not feedback:
            feedback.append(
                "The previous SQL did not fully "
                "satisfy the original question. "
                "Re-evaluate the complete request "
                "and generate a corrected SQL."
            )

        return tuple(feedback)