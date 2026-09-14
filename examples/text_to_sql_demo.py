from __future__ import annotations

import argparse
import os
from pathlib import Path

from sql_pilot_engine.app.sql_core_factory import build_trusted_sql_workflow
from sql_pilot_engine.app.text_to_sql_factory import build_text_to_sql_capability
from sql_pilot_engine.capabilities.text_to_sql import TextToSQLCapability
from sql_pilot_engine.config.llm import load_deepseek_settings
from sql_pilot_engine.context.builder import QueryContextBuilder
from sql_pilot_engine.context.mandatory_rules import MandatoryRuleMatcher
from sql_pilot_engine.context.semantic.loan_domain import (
    LOAN_DOMAIN_CONTEXT_DOCUMENTS,
    LOAN_MANDATORY_RULES,
)
from sql_pilot_engine.generation.deepseek_model import DeepSeekTextGenerationModel
from sql_pilot_engine.llm.clients import DeepSeekLLMClient, MockLLMClient
from sql_pilot_engine.llm.transport import OpenAICompatibleTransport
from sql_pilot_engine.metadata.demo_provider import build_loan_demo_metadata_provider
from sql_pilot_engine.observability.logging import configure_logging
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLRequest,
)


class FakePlannerModel:
    """Deterministic planner fixture used to verify the software call chain."""

    def generate(self, prompt: str) -> str:
        _ = prompt
        return """
        {
          "tables": ["odps_prd_dwd.ods_hd_100_cldkxx"],
          "dimensions": ["dt"],
          "metrics": ["tech_loan_balance"],
          "filters": [
            "is_high_tech_mfg_loan_code = '1'",
            "dt = '${p_month_yyyymm}'"
          ],
          "group_by": ["dt"]
        }
        """


class FakeSQLModel:
    """Deterministic SQL-generator fallback fixture for offline demos."""

    def generate(self, prompt: str) -> str:
        _ = prompt
        return """
        SELECT
            dt,
            SUM(loan_bal_rmb) AS tech_loan_balance
        FROM odps_prd_dwd.ods_hd_100_cldkxx
        WHERE is_high_tech_mfg_loan_code = '1'
          AND dt = '${p_month_yyyymm}'
        GROUP BY dt
        """


def build_demo_service(*, use_real_llm: bool) -> TextToSQLCapability:
    """
    Build the public Text-to-SQL demo with synthetic metadata only.

    The repository intentionally does not require a committed production metadata DB.
    Real LLM mode changes only model providers; physical metadata remains the same
    deterministic synthetic fixture so the demo is reproducible and safe to publish.
    """

    project_root = Path(__file__).resolve().parents[1]
    semantic_model_path = (
        project_root
        / "sql_pilot_engine"
        / "context"
        / "semantic"
        / "loan_model.json"
    )

    if use_real_llm:
        llm_settings = load_deepseek_settings()
        transport = OpenAICompatibleTransport(llm_settings.provider)

        planner_model = DeepSeekTextGenerationModel(
            transport=transport,
            request_config=llm_settings.text_request,
        )
        sql_model = planner_model
        structured_model = DeepSeekLLMClient(
            transport=transport,
            request_config=llm_settings.structured_request,
        )
        semantic_validator_model = structured_model
        llm_provider_name = llm_settings.provider.name
    else:
        planner_model = FakePlannerModel()
        sql_model = FakeSQLModel()
        structured_model = MockLLMClient()
        semantic_validator_model = None
        llm_provider_name = "mock"

    trusted_sql_workflow = build_trusted_sql_workflow(
        metadata_provider_factory=build_loan_demo_metadata_provider,
        default_enable_metadata=True,
        llm_client=structured_model,
        llm_provider_name=llm_provider_name,
    )

    context_builder = QueryContextBuilder(
        mandatory_rule_matcher=MandatoryRuleMatcher(
            LOAN_MANDATORY_RULES
        )
    )

    return build_text_to_sql_capability(
        semantic_model_path=semantic_model_path,
        context_documents=LOAN_DOMAIN_CONTEXT_DOCUMENTS,
        context_builder=context_builder,
        planner_model=planner_model,
        sql_model=sql_model,
        metadata_provider_factory=build_loan_demo_metadata_provider,
        semantic_validator_model=semantic_validator_model,
        collection_name="text_to_sql_demo",
        max_semantic_retries=1,
        trusted_sql_workflow=trusted_sql_workflow,
    )


def read_env_bool(
    name: str,
    *,
    default: bool = False,
) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False

    raise ValueError(
        f"{name} must be a boolean value, got: {raw!r}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent3.0 Text-to-SQL public release demo"
    )
    parser.add_argument(
        "--question",
        type=str,
        default="统计下本期高新技术企业的贷款余额",
        help="用户查询的业务问题。",
    )
    parser.add_argument(
        "--dialect",
        type=str,
        default="maxcompute",
        help="目标 SQL 方言。",
    )
    parser.add_argument(
        "--use-real-llm",
        action=argparse.BooleanOptionalAction,
        default=read_env_bool("AGENT3_USE_REAL_LLM"),
        help="是否调用真实大模型；默认离线 synthetic demo。",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="日志级别。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    service = build_demo_service(
        use_real_llm=args.use_real_llm
    )

    response = service.generate(
        TextToSQLRequest(
            question=args.question,
            dialect=args.dialect,
        )
    )

    while isinstance(response, TextToSQLClarification):
        print("\n[Agent needs clarification]")
        print(response.clarification_question)
        if response.reason:
            print("Reason:", response.reason)

        answer = input("\nYour clarification > ").strip()
        if not answer:
            print("No clarification supplied. Task stopped.")
            return

        if not response.thread_id:
            raise RuntimeError(
                "Clarification response has no thread_id."
            )

        response = service.resume(
            thread_id=response.thread_id,
            answer=answer,
        )

    result = response

    print("=" * 70)
    print("Agent3.0 · Text-to-SQL Demo")
    print("=" * 70)

    print("\n[1] User Question")
    print(result.question)

    print("\n[2] Query Plan")
    print("tables:", result.query_plan.tables)
    print("dimensions:", result.query_plan.dimensions)
    print("metrics:", result.query_plan.metrics)
    print("filters:", result.query_plan.filters)
    print("group_by:", result.query_plan.group_by)

    print("\n[3] Generation")
    print("source:", result.generation_source)
    print("compilation_status:", result.compilation_status)
    print(result.generated_sql)

    print("\n[4] SQL Validation")
    print("status:", result.validation_status)
    print("success:", result.success)

    print("\n[5] Semantic Validation")
    print("status:", result.semantic_validation_status)
    print("missing requirements:", result.semantic_missing_requirements)
    print("issues:", result.semantic_issues)

    print("\n[6] Trusted SQL")
    if result.trusted_sql is None:
        print("SQL 未通过可信审查，当前没有 Trusted SQL。")
    else:
        print(result.trusted_sql)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
