# sql_review_agent/app/factory.py

from sql_review_agent.engine import SQLReviewEngine
from sql_review_agent.llm.clients import create_llm_client
from sql_review_agent.metadata.provider import MockMetadataProvider
from sql_review_agent.rules.registry import RuleRegistry
from sql_review_agent.services.review_service import ReviewService
from sql_review_agent.services.sql_critic_service import SQLCriticService

from sql_review_agent.agents.sql_explain_agent import SQLExplainAgent
from sql_review_agent.llm.deepseek_client import DeepSeekLLMClient

from sql_review_agent.llm.json_repair import JSONRepairer

from sql_review_agent.workflow.sql_agent_workflow import SQLAgentWorkflow

import os

def build_explain_agent():
    provider = os.getenv("SQLPILOT_EXPLAIN_PROVIDER","mock").lower()

    if provider == "deepseek":
        llm_client = DeepSeekLLMClient.from_env()
        return SQLExplainAgent(
            llm_client=llm_client,
            json_repairer=JSONRepairer(llm_client=llm_client)
        )
    return None

def build_review_service(enable_llm: bool = False, llm_provider: str = "mock") -> ReviewService:
    registry = RuleRegistry()
    llm_client = None
    if enable_llm:
        llm_client = create_llm_client(llm_provider)
    return ReviewService(rule_registry=registry, llm_client=llm_client)


def build_sql_review_engine(enable_llm: bool = False, llm_provider: str = "mock") -> SQLReviewEngine:
    """构建统一 SQL Review Engine。

    CLI / FastAPI / Streamlit 后续都应优先依赖 Engine，而不是直接依赖
    ReviewService 的长参数方法。
    """
    service = build_review_service(enable_llm=enable_llm, llm_provider=llm_provider)
    return SQLReviewEngine(review_service=service, metadata_provider_factory=MockMetadataProvider, engine_agent=build_explain_agent(),critic_service=SQLCriticService(),)


def build_workflow(max_retries: int = 1,) -> SQLAgentWorkflow:
    engine = build_sql_review_engine()
    return SQLAgentWorkflow(engine=engine, max_retries=max_retries,)


def build_metadata_provider(enable_metadata: bool):
    if not enable_metadata:
        return None
    return MockMetadataProvider()
