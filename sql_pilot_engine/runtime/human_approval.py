from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class HumanApprovalStatus(str, Enum):
    """Stable status for an explicit Human-in-the-Loop approval gate."""

    AWAITING = "awaiting_human_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FEEDBACK = "feedback"
    BLOCKED_BY_MACHINE_GATE = "blocked_by_machine_gate"


@dataclass(frozen=True, slots=True)
class HumanApprovalRequest:
    """A candidate or interpretation that cannot cross the final gate automatically."""

    stage: str
    summary: str
    candidate_sql: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    machine_gate_passed: bool = True
    approval_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def status(self) -> HumanApprovalStatus:
        return HumanApprovalStatus.AWAITING


@dataclass(frozen=True, slots=True)
class HumanApprovalRecord:
    approval_id: str
    stage: str
    status: HumanApprovalStatus
    human_input: str
    candidate_sql: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    machine_gate_passed: bool = True

    @property
    def approved(self) -> bool:
        return (
            self.status is HumanApprovalStatus.APPROVED
            and self.machine_gate_passed
        )

    @property
    def human_approved_sql(self) -> str | None:
        """Only machine-pass + exact human APPROVE can materialize approved SQL."""

        if not self.approved:
            return None
        return self.candidate_sql

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "stage": self.stage,
            "status": self.status.value,
            "human_input": self.human_input,
            "candidate_sql": self.candidate_sql,
            "trace_id": self.trace_id,
            "metadata": dict(self.metadata),
            "machine_gate_passed": self.machine_gate_passed,
            "human_approved_sql": self.human_approved_sql,
        }


class HumanApprovalGate:
    """Fail-closed approval contract shared by local acceptance and future runtimes.

    Two conditions are mandatory for a final approved SQL:
    1. deterministic / machine safety gates have passed;
    2. the operator types the exact token ``APPROVE``.

    Human approval is therefore a final authorization step, not a bypass around failed
    Program / Review / Critic / Metadata / Lineage gates.
    """

    APPROVE_TOKEN = "APPROVE"
    REJECT_TOKEN = "REJECT"

    @classmethod
    def decide(
        cls,
        request: HumanApprovalRequest,
        human_input: str,
    ) -> HumanApprovalRecord:
        raw = human_input.strip()

        if not request.machine_gate_passed:
            status = HumanApprovalStatus.BLOCKED_BY_MACHINE_GATE
        elif raw == cls.APPROVE_TOKEN:
            status = HumanApprovalStatus.APPROVED
        elif raw == cls.REJECT_TOKEN:
            status = HumanApprovalStatus.REJECTED
        elif raw:
            status = HumanApprovalStatus.FEEDBACK
        else:
            status = HumanApprovalStatus.AWAITING

        return HumanApprovalRecord(
            approval_id=request.approval_id,
            stage=request.stage,
            status=status,
            human_input=raw,
            candidate_sql=request.candidate_sql,
            trace_id=request.trace_id,
            metadata=dict(request.metadata),
            machine_gate_passed=request.machine_gate_passed,
        )
