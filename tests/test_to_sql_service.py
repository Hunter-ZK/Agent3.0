from __future__ import annotations

from pathlib import Path

from sql_pilot_engine.app.text_to_sql_factory import (
    build_text_to_sql_service,
)
from sql_pilot_engine.context.models import (
    ContextDocument,
    ContextDocumentKind,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLRequest,
)


class FakePlannerModel:
    def generate(self, prompt: str) -> str:
        return """
        {
          "tables": ["dwd_order_detail"],
          "dimensions": ["user_id"],
          "metrics": ["total_order_amount"],
          "filters": [],
          "group_by": ["user_id"]
        }
        """


class FakeSQLModel:
    def generate(self, prompt: str) -> str:
        return """
        SELECT
            user_id,
            SUM(order_amount) AS total_order_amount
        FROM dwd_order_detail
        GROUP BY user_id
        """


class DangerousSQLModel:
    def generate(self, prompt: str) -> str:
        return "DROP TABLE dwd_order_detail"


def build_service(
    *,
    sql_model=None,
):
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
        / "sample_model.json"
    )

    documents = (
        ContextDocument(
            document_id="knowledge_order_amount",
            kind=ContextDocumentKind.BUSINESS_KNOWLEDGE,
            text=(
                "订单金额对应字段 "
                "dwd_order_detail.order_amount。"
            ),
            metadata={"domain": "order"},
        ),
        ContextDocument(
            document_id="verified_user_amount",
            kind=ContextDocumentKind.VERIFIED_SQL,
            text=(
                "问题：统计每个用户订单总金额。"
                "SQL：SELECT user_id, "
                "SUM(order_amount) "
                "FROM dwd_order_detail "
                "GROUP BY user_id"
            ),
            metadata={"domain": "order"},
        ),
    )

    return build_text_to_sql_service(
        semantic_model_path=semantic_model_path,
        context_documents=documents,
        planner_model=FakePlannerModel(),
        sql_model=sql_model or FakeSQLModel(),
        semantic_validator_model=None,
        collection_name="text_to_sql_service_test",
        max_sql_retries=0,
        max_semantic_retries=1,
    )


def test_text_to_sql_pipeline_returns_trusted_sql():
    service = build_service()

    result = service.generate(
        TextToSQLRequest(
            question="统计每个用户订单总金额"
        )
    )


    assert result.success is True
    assert result.validation_status == "no_issue"
    assert result.query_plan.tables == (
        "dwd_order_detail",
    )
    assert result.query_plan.group_by == (
        "user_id",
    )
    assert result.trusted_sql is not None
    assert "DWD_ORDER_DETAIL" in result.trusted_sql.upper()


def test_text_to_sql_pipeline_blocks_dangerous_sql():
    service = build_service(
        sql_model=DangerousSQLModel(),
    )

    result = service.generate(
        TextToSQLRequest(
            question="删除订单表"
        )
    )

    assert result.success is False
    assert result.validation_status == "blocked"
    assert result.trusted_sql is None
