from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.services.review_service import (
    ReviewService,
)


def test_review_service_passes_query_context_to_llm_review():
    query_context = QueryContext(
        question=(
            "统计本期高新技术企业贷款余额"
        ),
        semantic_context=(
            "TABLE ods_hd_100_cldkxx"
        ),
        business_knowledge=(),
        verified_sql=(),
        session_context=(),
    )

    service = ReviewService()

    captured = {}

    def fake_run_llm_review(
        *,
        sql,
        file_path,
        deterministic_issues,
        analysis_context_text,
        metadata_context_text,
        query_context=None,
        rule_packs=(),
    ):
        captured[
            "query_context"
        ] = query_context

        return []

    service.run_llm_review = (
        fake_run_llm_review
    )

    result = service.review_sql(
        sql=(
            "SELECT loan_iou_no "
            "FROM ods_hd_100_cldkxx"
        ),
        enable_llm=True,
        query_context=query_context,
    )

    assert (
        captured["query_context"]
        is query_context
    )

    assert result is not None