import sql_pilot_engine.app.sql_review_factory as factory_module

from sql_pilot_engine.capabilities.sql_review import (
    SQLReviewService,
)


class DummyWorkflow:
    pass


class DummyMetadataProvider:
    pass


def test_factory_disables_metadata_without_provider(
    monkeypatch,
):
    captured = {}

    def fake_build_workflow(
        **kwargs,
    ):
        captured.update(
            kwargs
        )

        return DummyWorkflow()

    monkeypatch.setattr(
        factory_module,
        "build_workflow",
        fake_build_workflow,
    )

    service = (
        factory_module
        .build_sql_review_service()
    )

    assert isinstance(
        service,
        SQLReviewService,
    )

    assert (
        captured[
            "default_enable_metadata"
        ]
        is False
    )

    assert (
        captured[
            "metadata_provider_factory"
        ]
        is None
    )


def test_factory_enables_metadata_with_provider(
    monkeypatch,
):
    captured = {}

    def fake_build_workflow(
        **kwargs,
    ):
        captured.update(
            kwargs
        )

        return DummyWorkflow()

    monkeypatch.setattr(
        factory_module,
        "build_sql_agent_workflow",
        fake_build_workflow,
    )

    def provider_factory():
        return DummyMetadataProvider()

    service = (
        factory_module
        .build_sql_review_service(
            metadata_provider_factory=(
                provider_factory
            )
        )
    )

    assert isinstance(
        service,
        SQLReviewService,
    )

    assert (
        captured[
            "default_enable_metadata"
        ]
        is True
    )

    assert (
        captured[
            "metadata_provider_factory"
        ]
        is provider_factory
    )