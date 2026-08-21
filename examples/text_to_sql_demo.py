from __future__ import annotations

from pathlib import Path
import argparse
import os





from sql_pilot_engine.llm.deepseek_client import (
    DeepSeekLLMClient,
)
from sql_pilot_engine.observability.logging import (
    configure_logging,
)
from sql_pilot_engine.context.semantic.loan_domain import (
    LOAN_DOMAIN_CONTEXT_DOCUMENTS,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLRequest,
)
from sql_pilot_engine.services.text_to_sql_service import (
    TextToSQLService,
)
from sql_pilot_engine.app.text_to_sql_factory import (
    build_text_to_sql_service,
)
from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)

# ============================================================
# 1. Demo专用Fake模型
# ============================================================
#
# 当前Demo的目标是验证Agent3.0的软件调用链，
# 而不是验证某个真实大模型的Text-to-SQL能力。
#
# 所以这里只Fake LLM。
# Context / Qdrant / Retriever / Planner代码 /
# Generator代码 / SQL Validation Workflow全部使用真实实现。
# ============================================================


class FakePlannerModel:
    """模拟Planner使用的LLM。

    固定返回一个结构化Query Plan。

    对应问题：
    “统计每个用户订单总金额”
    """

    def generate(
        self,
        prompt: str,
    ) -> str:
        return """
        {
        "tables": [
            "dwd_hd_101_cldwdk"
        ],
        "dimensions": [
            "dt"
        ],
        "metrics": [
            "tech_loan_balance"
        ],
        "filters": [
            "is_high_tech_ent_loan_code = '1'",
            "dt = '${p_month_yyyymm}'"
        ],
        "group_by": [
            "dt"
        ]
        }
        """


class FakeSQLModel:
    """模拟SQL Generator使用的LLM。"""

    def generate(
        self,
        prompt: str,
    ) -> str:
        return """
        SELECT
            SUM(loan_bal_rmb) AS loan_bal_rmb,
            dt
        FROM dwd_hd_101_cldwdk
        WHERE is_high_tech_ent_loan_code = '1'
        AND dt = '${p_month_yyyymm}'
        GROUP BY dt
        """



# ============================================================
# 2. 构建Text-to-SQL产品能力
# ============================================================

def build_demo_service(
    use_real_llm: bool,
) -> TextToSQLService:

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    metadata_db_path = (
        project_root
        / "data"
        / "metadata"
        / "agent_metadata.db"
    )

    def build_metadata_provider():
        return SQLiteMetadataRepository(
            metadata_db_path
        )


    if not metadata_db_path.is_file():
        raise FileNotFoundError(
            "Metadata database not found: "
            f"{metadata_db_path}"
        )

    semantic_model_path = (
        project_root
        / "sql_pilot_engine"
        / "context"
        / "semantic"
        / "loan_model.json"
    )

    if use_real_llm:

        model = (
            DeepSeekLLMClient
            .from_env()
        )

        planner_model = model
        sql_model = model

        semantic_validator_model = (
            model
        )

    else:

        planner_model = (
            FakePlannerModel()
        )

        sql_model = (
            FakeSQLModel()
        )

        semantic_validator_model = None

    return build_text_to_sql_service(
        semantic_model_path=(
            semantic_model_path
        ),

        context_documents=(
            LOAN_DOMAIN_CONTEXT_DOCUMENTS
        ),

        metadata_provider_factory=(
            build_metadata_provider
        ),

        planner_model=(
            planner_model
        ),

        sql_model=(
            sql_model
        ),

        semantic_validator_model=(
            semantic_validator_model
        ),

        collection_name=(
            "text_to_sql_demo"
        ),

        max_sql_retries=0,

        max_semantic_retries=1,
    )

def parse_args() -> argparse.Namespace:

    env_use_real_llm = read_env_bool("AGENT3_USE_REAL_LLM")

    parser = argparse.ArgumentParser(description="Agent3.0 Text-to-SQL Demo 运行工具")

    parser.add_argument(
        "--question",
        type=str,
        default="统计下本期高新技术企业的贷款余额",
        help="用户查询的业务问题",
    )
    parser.add_argument(
        "--dialect",
        type=str,
        default="maxcompute",
        help="目标 SQL 方言 (如: maxcompute, postgresql, mysql, snowflake)",
    )
    
    # 支持 --use-real-llm 与 --no-real-llm 互斥控制
    parser.add_argument(
        "--use-real-llm",
        action=argparse.BooleanOptionalAction,
        default=env_use_real_llm,
        help="是否使用真实大模型 (默认读取 AGENT3_USE_REAL_LLM 环境变量)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="设置日志输出级别 (默认: INFO)",
    )

    return parser.parse_args()


def read_env_bool(
    name: str,
    *,
    default: bool = False,
):
    raw = os.getenv(name)

    if raw is None:
        return default

    value = raw.strip().lower()

    if value in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if value in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise ValueError(
        f"{name} must be a boolean value, "
        f"got: {raw!r}"
    )

# ============================================================
# 3. Demo主流程
# ============================================================


def main() -> None:

    args = parse_args()
    configure_logging(args.log_level)

    service = build_demo_service(use_real_llm=args.use_real_llm)

    session_context: list[str] = []
    

    response = service.generate(
        TextToSQLRequest(
            question=args.question,
            dialect=args.dialect,
        )
    )

    while isinstance(
        response,
        TextToSQLClarification,
    ):

        print()
        print(
            "[Agent needs clarification]"
        )

        print(
            response.clarification_question
        )

        if response.reason:
            print(
                "Reason:",
                response.reason,
            )

        answer = input(
            "\nYour clarification > "
        ).strip()

        if not answer:
            print(
                "No clarification supplied. "
                "Task stopped."
            )

            return

        if not response.thread_id:
            raise RuntimeError(
                "Clarification response "
                "has no thread_id."
            )

        response = service.resume(
            thread_id=(
                response.thread_id
            ),

            answer=answer,
        )


    result = response
    

    print("=" * 70)
    print("Agent3.0 · Text-to-SQL Demo")
    print("=" * 70)

    print("\n[1] User Question")
    print(result.question)

    print("\n[2] Query Plan")

    print(
        "tables:",
        result.query_plan.tables,
    )

    print(
        "dimensions:",
        result.query_plan.dimensions,
    )

    print(
        "metrics:",
        result.query_plan.metrics,
    )

    print(
        "filters:",
        result.query_plan.filters,
    )

    print(
        "group_by:",
        result.query_plan.group_by,
    )

    print("\n[3] Generated SQL")
    print(result.generated_sql)

    print("\n[4] SQL Validation")
    print(
        "status:",
        result.validation_status,
    )

    print(
        "success:",
        result.success,
    )
    
    print(
        "\n[5] Semantic Validation"
    )

    print(
        "status:",
        result.semantic_validation_status,
    )

    print(
        "missing requirements:",
        result.semantic_missing_requirements,
    )

    print(
        "issues:",
        result.semantic_issues,
    )

    print("\n[6] Trusted SQL")

    if result.trusted_sql is None:
        print(
            "SQL未通过可信审查，"
            "当前没有Trusted SQL。"
        )
    else:
        print(result.trusted_sql)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()