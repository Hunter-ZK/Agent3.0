from sql_pilot_engine.runtime.human_approval import (
    HumanApprovalGate,
    HumanApprovalRequest,
    HumanApprovalStatus,
)


def _request() -> HumanApprovalRequest:
    return HumanApprovalRequest(
        stage="final_sql",
        summary="candidate",
        candidate_sql="SELECT 1",
        trace_id="trace-1",
    )


def test_exact_approve_materializes_human_approved_sql() -> None:
    record = HumanApprovalGate.decide(_request(), "APPROVE")

    assert record.status is HumanApprovalStatus.APPROVED
    assert record.approved is True
    assert record.human_approved_sql == "SELECT 1"


def test_convenience_words_never_count_as_approval() -> None:
    for value in ("approve", "yes", "y", "ok", "", "  "):
        record = HumanApprovalGate.decide(_request(), value)
        assert record.status is not HumanApprovalStatus.APPROVED
        assert record.human_approved_sql is None


def test_reject_never_materializes_sql() -> None:
    record = HumanApprovalGate.decide(_request(), "REJECT")

    assert record.status is HumanApprovalStatus.REJECTED
    assert record.human_approved_sql is None


def test_non_control_text_is_feedback_not_approval() -> None:
    record = HumanApprovalGate.decide(
        _request(),
        "Please keep the original partition logic.",
    )

    assert record.status is HumanApprovalStatus.FEEDBACK
    assert record.human_approved_sql is None
