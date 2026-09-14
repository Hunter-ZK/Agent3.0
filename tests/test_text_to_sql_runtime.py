from __future__ import annotations

from examples.text_to_sql_demo import build_demo_service
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLResult,
    TextToSQLRequest,
)


def test_text_to_sql_checkpoint_resume_after_clarification() -> None:
    """Release gate for LangGraph interrupt/checkpoint/resume semantics."""

    service = build_demo_service(use_real_llm=False)

    first = service.generate(
        TextToSQLRequest(
            question="统计贷款余额",
            dialect="maxcompute",
        )
    )

    assert isinstance(first, TextToSQLClarification)
    assert first.thread_id
    assert "科技贷款" in first.clarification_question
    assert "绿色贷款" in first.clarification_question

    resumed = service.resume(
        thread_id=first.thread_id,
        answer="绿色贷款",
    )

    assert isinstance(resumed, TextToSQLResult)
    assert resumed.success is True
    assert resumed.query_plan.tables == (
        "odps_prd_dwd.ods_hd_200_cldkxx",
    )
    assert resumed.query_plan.metrics == (
        "green_loan_balance",
    )
    assert resumed.trusted_sql is not None
    assert "ods_hd_200_cldkxx" in resumed.trusted_sql.lower()
