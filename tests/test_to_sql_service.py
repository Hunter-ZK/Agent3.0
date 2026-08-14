class FakePlannerModel:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return """
        {
          "tables": [
            "dwd_order_detail"
          ],
          "dimensions": [
            "user_id"
          ],
          "metrics": [
            "total_order_amount"
          ],
          "filters": [],
          "group_by": [
            "user_id"
          ]
        }
        """


class FakeSQLModel:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return """
        SELECT
            user_id,
            SUM(order_amount)
                AS total_order_amount
        FROM dwd_order_detail
        GROUP BY user_id
        """
        
        
from pathlib import Path

from sql_pilot_engine.app.factory import (
    build_workflow,
)
from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)
from sql_pilot_engine.context.embedding import (
    TokenHashEmbeddingProvider,
)
from sql_pilot_engine.context.models import (
    ContextDocument,
    ContextDocumentKind,
)
from sql_pilot_engine.context.qdrant_store import (
    QdrantVectorStore,
)
from sql_pilot_engine.context.retriever import (
    KnowledgeRetriever,
    VerifiedSQLRetriever,
)
from sql_pilot_engine.context.semantic.loader import (
    SemanticModelLoader,
)
from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)
from sql_pilot_engine.generation.sql_generator import (
    SQLGenerator,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLRequest,
)
from sql_pilot_engine.services.text_to_sql_service import (
    TextToSQLService,
)


def build_service() -> TextToSQLService:

    embedding = TokenHashEmbeddingProvider(
        dimensions=128
    )

    vector_store = QdrantVectorStore(
        embedding_provider=embedding,
        collection_name="text_to_sql_test",
    )

    vector_store.add(
        [
            ContextDocument(
                document_id="knowledge_order_amount",
                kind=(
                    ContextDocumentKind
                    .BUSINESS_KNOWLEDGE
                ),
                text=(
                    "订单金额对应字段 "
                    "dwd_order_detail.order_amount。"
                ),
                metadata={
                    "domain": "order"
                },
            ),

            ContextDocument(
                document_id="verified_user_amount",
                kind=(
                    ContextDocumentKind
                    .VERIFIED_SQL
                ),
                text=(
                    "问题：统计每个用户订单总金额。"
                    "SQL：SELECT user_id, "
                    "SUM(order_amount) "
                    "FROM dwd_order_detail "
                    "GROUP BY user_id"
                ),
                metadata={
                    "domain": "order"
                },
            ),
        ]
    )

    semantic_model = (
        SemanticModelLoader()
        .load(
            "sql_pilot_engine/"
            "context/semantic/"
            "sample_model.json"
        )
    )

    return TextToSQLService(
        semantic_model=semantic_model,

        knowledge_retriever=(
            KnowledgeRetriever(
                vector_store
            )
        ),

        verified_sql_retriever=(
            VerifiedSQLRetriever(
                vector_store
            )
        ),

        context_builder=(
            QueryContextBuilder()
        ),

        planner=QueryPlanner(
            model=FakePlannerModel()
        ),

        sql_generator=SQLGenerator(
            model=FakeSQLModel()
        ),

        validation_workflow=(
            build_workflow(
                max_retries=0
            )
        ),
    )
    
    
def test_text_to_sql_pipeline_returns_trusted_sql():

    service = build_service()

    result = service.generate(
        TextToSQLRequest(
            question=(
                "统计每个用户订单总金额"
            )
        )
    )

    assert result.success is True

    assert (
        result.validation_status
        == "no_issue"
    )

    assert (
        result.query_plan.tables
        == ("dwd_order_detail",)
    )

    assert (
        result.query_plan.group_by
        == ("user_id",)
    )

    assert result.trusted_sql is not None

    assert (
        "DWD_ORDER_DETAIL"
        in result.trusted_sql.upper()
    )
    
    
class DangerousSQLModel:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return (
            "DROP TABLE "
            "dwd_order_detail"
        )
        
        
        
def test_text_to_sql_pipeline_blocks_dangerous_sql():

    service = build_service()

    service.sql_generator = (
        SQLGenerator(
            model=DangerousSQLModel()
        )
    )

    result = service.generate(
        TextToSQLRequest(
            question="删除订单表"
        )
    )

    assert result.success is False

    assert (
        result.validation_status
        == "blocked"
    )

    assert result.trusted_sql is None