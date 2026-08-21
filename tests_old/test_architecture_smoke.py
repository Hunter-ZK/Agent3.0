import inspect


def test_target_architecture_can_be_imported():
    from sql_pilot_engine.engine import (
        SQLPilotEngine,
    )
    from sql_pilot_engine.services.fix_service import (
        FixService,
    )
    from sql_pilot_engine.services.review_service import (
        ReviewService,
    )
    from sql_pilot_engine.services.critic_service import (
        CriticService,
    )
    from sql_pilot_engine.workflow.sql_agent_workflow import (
        SQLAgentWorkflow,
    )

    assert FixService is not None
    assert ReviewService is not None
    assert CriticService is not None
    assert SQLAgentWorkflow is not None


def test_engine_has_final_dependency_boundaries():
    from sql_pilot_engine.engine import SQLPilotEngine

    parameters = inspect.signature(
        SQLPilotEngine.__init__
    ).parameters

    assert "review_service" in parameters
    assert "fix_service" in parameters
    assert "explain_agent" in parameters
    assert "critic_service" in parameters
    assert "engine_agent" not in parameters


def test_review_service_no_longer_accepts_fix_options():
    from sql_pilot_engine.services.review_service import (
        ReviewService,
    )

    parameters = inspect.signature(
        ReviewService.review_sql
    ).parameters

    assert "fix_sql" not in parameters
    assert "fix_provider" not in parameters