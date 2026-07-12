from sql_review_agent.core.execution_context import ReviewExecutionContext
from sql_review_agent.schemas import SQLFixRequest,SQLReviewRequest

def test_context_from_review_request_should_keep_review_fields():
    request = SQLReviewRequest(
        sql = "select 1",
        file_path = "memory.sql",
        mode = "dev",
        dialect="maxcompute",
        categories={"basic"},
        enable_metadata=True,

        enable_llm=True,
        llm_provider="mock",
    )

    context = ReviewExecutionContext.from_review_request(request)

    assert context.sql == "select 1"
    assert context.file_path == "memory.sql"
    assert context.mode == "dev"
    assert context.dialect == "maxcompute"
    assert context.categories == {"basic"}
    assert context.enable_metadata is True
    assert context.enable_llm is True
    assert context.llm_provider == "mock"
    assert context.fix_sql is False
    assert context.trace_id is not None

def test_context_from_fix_request_should_enable_fix():
    request = SQLFixRequest(
        sql="select * from t",
        categories={'basic'},
        file_path="fix.sql",
        fix_provider="auto",
        enable_llm=True,
    )

    context = ReviewExecutionContext.from_fix_request(request)

    assert context.sql == "select * from t"
    assert context.file_path == "fix.sql"
    assert context.categories == {"basic"}
    assert context.enable_llm is True
    assert context.llm_provider == "mock"
    assert context.fix_sql is True
    assert context.fix_provider == "auto"
    assert context.trace_id is not None

def test_context_should_generate_independent_trace_id():
    context_a = ReviewExecutionContext(sql="select 1")
    context_b = ReviewExecutionContext(sql="select 2")

    assert context_a.trace_id != context_b.trace_id


def test_context_retrieved_docs_should_not_be_shared_between_tasks():
    context_a = ReviewExecutionContext(sql="select 1")
    context_b = ReviewExecutionContext(sql="select 2")

    context_a.retrieved_docs.append(
        {
            "title": "口径规范",
            "content": "data_type=fs 表示发生额",
        }
    )

    assert context_b.retrieved_docs == []


    