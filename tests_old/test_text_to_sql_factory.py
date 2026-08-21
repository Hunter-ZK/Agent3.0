from __future__ import annotations

from pathlib import Path

from sql_pilot_engine.app.text_to_sql_factory import (
    build_text_to_sql_service,
)
from sql_pilot_engine.context.semantic.loan_domain import (
    LOAN_DOMAIN_CONTEXT_DOCUMENTS,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLRequest,
    TextToSQLResult,
)


class FakePlannerModel:
    def generate(
        self,
        prompt: str,
    ) -> str:
        return """
        {
          "status": "ready",
          "plan": {
            "tables": [
              "dwd_hd_201_cldwdk"
            ],
            "dimensions": [
              "dt"
            ],
            "metrics": [
              "green_loan_balance"
            ],
            "filters": [
              "dt = '${p_month_yyyymm}'"
            ],
            "group_by": [
              "dt"
            ]
          }
        }
        """


class FakeSQLModel:
    def generate(
        self,
        prompt: str,
    ) -> str:
        return """
        SELECT
            SUM(loan_bal_rmb) AS green_loan_balance,
            dt
        FROM dwd_hd_201_cldwdk
        WHERE dt = '${p_month_yyyymm}'
        GROUP BY dt
        """


def test_factory_builds_working_service():
    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    semantic_model_path = (
        project_root
        / "sql_pilot_engine"
        / "context"
        / "semantic"
        / "loan_model.json"
    )

    service = (
        build_text_to_sql_service(
            semantic_model_path=(
                semantic_model_path
            ),

            context_documents=(
                LOAN_DOMAIN_CONTEXT_DOCUMENTS
            ),

            planner_model=(
                FakePlannerModel()
            ),

            sql_model=(
                FakeSQLModel()
            ),

            # 本测试只验证Composition Root，
            # 不调用真实LLM Semantic Validator。
            semantic_validator_model=None,

            collection_name=(
                "factory_test"
            ),

            max_sql_retries=0,

            max_semantic_retries=0,
        )
    )

    response = service.generate(
        TextToSQLRequest(
            question=(
                "统计本期绿色贷款余额"
            )
        )
    )

    assert isinstance(
        response,
        TextToSQLResult,
    )

    assert response.query_plan.tables == (
        "dwd_hd_201_cldwdk",
    )

    assert response.query_plan.metrics == (
        "green_loan_balance",
    )

    assert (
        response.generated_sql
        is not None
    )

    assert response.success is True

    assert (
        response.trusted_sql
        is not None
    )