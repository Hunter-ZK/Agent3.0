import os

from collections.abc import Callable

from sql_pilot_engine.metadata.provider import (
    MetadataProvider,
)

from sql_pilot_engine.agents.sql_explain_agent import (
    SQLExplainAgent,
)
from sql_pilot_engine.engine import SQLPilotEngine
from sql_pilot_engine.llm.clients import (
    create_llm_client,
)
from sql_pilot_engine.llm.deepseek_client import (
    DeepSeekLLMClient,
)
from sql_pilot_engine.llm.json_repair import (
    JSONRepairer,
)
from sql_pilot_engine.metadata import (
    MockMetadataProvider,
)
from sql_pilot_engine.rules.registry import RuleRegistry
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

from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
)
from sql_pilot_engine.optimization.context import (
    OptimizationContext,
)



def build_explain_agent():
    provider = os.getenv(
        "SQLPILOT_EXPLAIN_PROVIDER",
        "mock",
    ).lower()

    if provider != "deepseek":
        return None

    llm_client = DeepSeekLLMClient.from_env()

    return SQLExplainAgent(
        llm_client=llm_client,
        json_repairer=JSONRepairer(
            llm_client=llm_client
        ),
    )


def build_sql_pilot_engine(
    enable_llm: bool = False,
    llm_provider: str = "mock",
    metadata_provider_factory: (
        Callable[
            [],
            MetadataProvider,
        ] | None
    ) = None,
) -> SQLPilotEngine:
    llm_client = (
        create_llm_client(llm_provider)
        if enable_llm
        else None
    )

    review_service = ReviewService(
        rule_registry=RuleRegistry(),
        llm_client=llm_client,
    )

    fix_service = FixService(
        review_service=review_service,
        llm_client=llm_client,
    )

    optimize_service = (
        OptimizeService(
            llm_client=llm_client
        )
        if llm_client is not None
        else None
    )

    return SQLPilotEngine(
        review_service=review_service,
        fix_service=fix_service,
        metadata_provider_factory=(
            metadata_provider_factory or
            MockMetadataProvider
        ),
        explain_agent=build_explain_agent(),
        optimize_service=optimize_service,
        critic_service=CriticService(),
    )


# 保留旧函数名兼容CLI和现有调用方。
def build_sql_review_engine(
    enable_llm: bool = False,
    llm_provider: str = "mock",
) -> SQLPilotEngine:
    return build_sql_pilot_engine(
        enable_llm=enable_llm,
        llm_provider=llm_provider,
    )


def build_workflow(
    max_retries: int = 1,
    *,
    metadata_provider_factory: (
        Callable[
            [],
            MetadataProvider,
        ] | None
    ) = None,
    default_enable_metadata:bool = False,
) -> SQLAgentWorkflow:

    optimization_metadata_provider = (
        metadata_provider_factory()
        if metadata_provider_factory
        is not None
        else None
    )

    optimizer = StaticSQLOptimizer(
        analysis_adapter=(
            SQLAnalysisAdapter()
        ),
        rule_registry=(
            build_default_optimization_registry()
        ),
        rewriter=(
            SafeSQLRewriter()
        ),
        context=(
            OptimizationContext(
                metadata_provider=(
                    optimization_metadata_provider
                )
            )
        ),
    )
    
    return SQLAgentWorkflow(
        engine=build_sql_pilot_engine(
            metadata_provider_factory=(
                metadata_provider_factory
            )
        ),
        optimizer=optimizer,
        max_retries=max_retries,
        default_enable_metadata=default_enable_metadata,
    )


def build_metadata_provider(
    enable_metadata: bool,
):
    if not enable_metadata:
        return None

    return MockMetadataProvider()