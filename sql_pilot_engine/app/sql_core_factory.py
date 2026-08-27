from sql_pilot_engine.engine import SQLPilotEngine


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
from sql_pilot_engine.workflow.trusted_sql_workflow import (
    TrustedSQLWorkflow,
)
 


def build_sql_pilot_engine(
    *,
    llm_client=None,
    metadata_provider_factory=None,
) -> SQLPilotEngine:

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


def build_trusted_sql_workflow(
    max_retries: int = 1,
    *,
    metadata_provider_factory=None,
    default_enable_metadata: bool = False,
    llm_client = None,
    llm_provider_name: str = "none",
) -> TrustedSQLWorkflow:
    
    enable_llm = (
        llm_client is not None
    )

    engine = build_sql_pilot_engine(
        llm_client=llm_client,
        metadata_provider_factory=(
            metadata_provider_factory
        ),
    )

    return TrustedSQLWorkflow(
        engine=engine,
        max_retries=max_retries,
        default_enable_metadata=(
            default_enable_metadata
        ),
        default_enable_llm=(
            enable_llm
        ),
        default_llm_provider=(
            llm_provider_name
        ),
        default_fix_provider=(
            "llm"
            if enable_llm
            else "auto"
        ),
    )

