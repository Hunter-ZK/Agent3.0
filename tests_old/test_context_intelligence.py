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
from sql_pilot_engine.context.semantic.renderer import (
    SemanticModelRenderer,
)


def build_store():
    embedding = (
        TokenHashEmbeddingProvider(
            dimensions=128
        )
    )

    store = QdrantVectorStore(
        embedding_provider=embedding,
        collection_name=(
            "test_agent3_context"
        ),
    )

    store.add(
        [
            ContextDocument(
                document_id="knowledge_order_amount",
                kind=(
                    ContextDocumentKind
                    .BUSINESS_KNOWLEDGE
                ),
                text=(
                    "订单金额指订单实际成交金额，"
                    "对应字段 "
                    "dwd_order_detail.order_amount。"
                ),
                metadata={
                    "domain": "order"
                },
            ),

            ContextDocument(
                document_id="knowledge_user",
                kind=(
                    ContextDocumentKind
                    .BUSINESS_KNOWLEDGE
                ),
                text=(
                    "用户通过user_id唯一标识。"
                ),
                metadata={
                    "domain": "user"
                },
            ),

            ContextDocument(
                document_id="sql_user_amount",
                kind=(
                    ContextDocumentKind
                    .VERIFIED_SQL
                ),
                text=(
                    "问题：统计每个用户的订单总金额。"
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

    return store


def test_semantic_model_loads():
    model = (
        SemanticModelLoader()
        .load(
            "sql_pilot_engine/"
            "context/semantic/"
            "sample_model.json"
        )
    )

    assert len(model.tables) == 1

    table = model.get_table(
        "dwd_order_detail"
    )

    assert table is not None

    assert (
        table.columns[2].name
        == "order_amount"
    )


def test_business_knowledge_retrieval():
    store = build_store()

    retriever = (
        KnowledgeRetriever(store)
    )

    results = retriever.retrieve(
        "订单金额应该使用哪个字段？",
        top_k=2,
    )

    assert results

    assert (
        results[0]
        .document
        .document_id
        == "knowledge_order_amount"
    )


def test_verified_sql_retrieval():
    store = build_store()

    retriever = (
        VerifiedSQLRetriever(store)
    )

    results = retriever.retrieve(
        "统计用户订单总金额",
        top_k=1,
    )

    assert results

    assert (
        results[0]
        .document
        .document_id
        == "sql_user_amount"
    )
    
    
def test_semantic_model_can_render():
    model = (
        SemanticModelLoader()
        .load(
            "sql_pilot_engine/"
            "context/semantic/"
            "sample_model.json"
        )
    )

    rendered = (
        SemanticModelRenderer()
        .render(model)
    )

    assert (
        "TABLE dwd_order_detail"
        in rendered
    )

    assert (
        "COLUMN order_amount"
        in rendered
    )

    assert (
        "METRIC total_order_amount"
        in rendered
    )