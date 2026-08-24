from __future__ import annotations

from collections.abc import (
    Callable,
)

from sql_pilot_engine.app.sql_core_factory import (
    build_sql_agent_workflow,
)
from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)
from sql_pilot_engine.capabilities.sql_review import (
    SQLReviewCapability,
)


def build_sql_review_capability(
    *,
    metadata_provider_factory: (
        Callable[
            [],
            MetadataProvider,
        ]
        | None
    ) = None,
    max_sql_retries: int = 1,
) -> SQLReviewCapability:
    """
    SQL Review Capability Composition Root。

    SQLReviewCapability 不负责创建：

    - Metadata Provider
    - SQL Engine
    - Workflow

    所有依赖统一在 app 层装配。
    """

    workflow = build_sql_agent_workflow(
        max_retries=(
            max_sql_retries
        ),
        metadata_provider_factory=(
            metadata_provider_factory
        ),
        default_enable_metadata=(
            metadata_provider_factory
            is not None
        ),
    )

    return SQLReviewCapability(
        workflow=workflow
    )