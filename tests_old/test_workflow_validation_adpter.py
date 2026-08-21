from types import SimpleNamespace

from sql_pilot_engine.runtime.workflow_validation_adapter import (
    WorkflowSQLValidationAdapter,
)


class FakeWorkflow:
    def __init__(
        self,
        result,
    ) -> None:
        self.result = result

    def run(
        self,
        sql: str,
    ):
        return self.result


def test_success_without_fix_uses_original_sql():
    workflow = FakeWorkflow(
        SimpleNamespace(
            success=True,
            final_status="no_issue",
            fix_response=None,
        )
    )

    adapter = WorkflowSQLValidationAdapter(
        workflow=workflow,
    )

    result = adapter.validate(
        sql="SELECT 1",
        dialect="maxcompute",
    )

    assert result.accepted is True
    assert result.final_sql == "SELECT 1"
    assert result.status == "no_issue"


def test_success_with_fix_uses_fixed_sql():
    workflow = FakeWorkflow(
        SimpleNamespace(
            success=True,
            final_status="fix_verified",
            fix_response=SimpleNamespace(
                fixed_sql="SELECT 2",
            ),
        )
    )

    adapter = WorkflowSQLValidationAdapter(
        workflow=workflow,
    )

    result = adapter.validate(
        sql="SELECT 1",
        dialect="maxcompute",
    )

    assert result.accepted is True
    assert result.final_sql == "SELECT 2"