import os

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
from sql_pilot_engine.metadata.provider import (
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
    SQLCriticService,
)
from sql_pilot_engine.workflow.sql_agent_workflow import (
    SQLAgentWorkflow,
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

    return SQLPilotEngine(
        review_service=review_service,
        fix_service=fix_service,
        metadata_provider_factory=(
            MockMetadataProvider
        ),
        explain_agent=build_explain_agent(),
        critic_service=SQLCriticService(),
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
) -> SQLAgentWorkflow:
    return SQLAgentWorkflow(
        engine=build_sql_pilot_engine(),
        max_retries=max_retries,
    )


def build_metadata_provider(
    enable_metadata: bool,
):
    if not enable_metadata:
        return None

    return MockMetadataProvider()