# sql_review_agent/reviewer.py

from sql_review_agent.app.factory import build_sql_review_engine
from sql_review_agent.schemas import SQLFixRequest, SQLReviewRequest


def review_sql(
    sql: str,
    file_path: str = "<memory>",
    categories: set[str] | None = None,
    mode: str = "prod",
    enable_llm: bool = False,
    llm_provider: str = "mock",
    metadata_provider=None,
    fix_sql: bool = False,
    fix_provider: str = "auto",
    **kwargs,
):
    """兼容旧版函数入口。

    新代码应优先使用 SQLReviewEngine；该函数保留给历史调用方。
    """
    engine = build_sql_review_engine(
        enable_llm=enable_llm or fix_provider == "llm",
        llm_provider=llm_provider,
    )

    request_kwargs = {
        "sql": sql,
        "file_path": file_path,
        "mode": mode,
        "categories": categories,
        "enable_metadata": metadata_provider is not None,
        "enable_llm": enable_llm,
        "llm_provider": llm_provider,
        "metadata_provider": metadata_provider,
    }

    if fix_sql:
        response = engine.fix(SQLFixRequest(**request_kwargs, fix_provider=fix_provider))
    else:
        response = engine.review(SQLReviewRequest(**request_kwargs))

    if not response.success or response.raw_result is None:
        raise RuntimeError(response.error_message or "SQL Review Engine 执行失败。")
    return response.raw_result
