from sql_pilot_engine.engine import SQLPilotEngine
from sql_pilot_engine.llm.clients import (
    create_llm_client,
)

from sql_pilot_engine.rules.registry import RuleRegistry
from sql_pilot_engine.services.explain_service import (
    ExplainService,
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
from sql_pilot_engine.services.optimize_service import (
    OptimizeService,
)
from sql_pilot_engine.workflow.sql_agent_workflow import (
    SQLAgentWorkflow,
)
 


def build_sql_pilot_engine(
    *,
    enable_llm: bool = True,
    llm_provider: str = "deepseek",
    metadata_provider_factory=None,
) -> SQLPilotEngine:

    llm_client = (
        create_llm_client(
            llm_provider
        )
        if enable_llm
        else None
    )

    review_service = ReviewService(
        rule_registry=RuleRegistry(),
        llm_client=llm_client,
    )

    fix_service = FixService(
        review_service=(
            review_service
        ),
        llm_client=llm_client,
    )

    explain_service = (
        ExplainService(
                llm_client=llm_client
            )
        if llm_client is not None
        else None
    )

    optimize_service = (
        OptimizeService(
            llm_client=llm_client
        )
        if llm_client is not None
        else None
    )

    return SQLPilotEngine(
        review_service=(
            review_service
        ),
        fix_service=fix_service,
        explain_service=(
            explain_service
        ),
        optimize_service=(
            optimize_service
        ),
        critic_service=(
            CriticService()
        ),
        metadata_provider_factory=(
            metadata_provider_factory
        ),
    )


def build_sql_agent_workflow(
    max_retries: int = 1,
    *,
    metadata_provider_factory=None,
    default_enable_metadata: bool = False,
    enable_llm: bool = True,
    llm_provider: str = "deepseek",
) -> SQLAgentWorkflow:

    engine = build_sql_pilot_engine(
        enable_llm=enable_llm,
        llm_provider=llm_provider,
        metadata_provider_factory=(
            metadata_provider_factory
        ),
    )

    return SQLAgentWorkflow(
        engine=engine,
        max_retries=max_retries,
        default_enable_metadata=(
            default_enable_metadata
        ),
        default_enable_llm=(
            enable_llm
        ),
        default_llm_provider=(
            llm_provider
        ),
        default_fix_provider=(
            "llm"
            if enable_llm
            else "auto"
        ),
    )

