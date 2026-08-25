from __future__ import annotations

from sql_pilot_engine.capabilities.text_to_sql import (
    TextToSQLCapability,
)
from sql_pilot_engine.generation.models import (
    QueryPlan,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLRequest,
    TextToSQLResult,
)


class FakeGraph:
    """
    模拟已经完成运行的 QueryAgentGraph。

    本测试不关心：
    - Planning
    - SQL Generation
    - Trusted SQL Workflow
    - Semantic Validator

    只验证：
    Graph State → Application Response
    的边界映射。
    """

    def start(
        self,
        *,
        thread_id: str,
        question: str,
        dialect: str,
        session_context: tuple[str, ...],
    ) -> dict:
        _ = thread_id
        _ = dialect
        _ = session_context

        return {
            "question": question,

            "query_plan": QueryPlan(
                tables=(
                    "ods_hd_100_cldkxx",
                ),
                dimensions=(),
                metrics=(
                    "tech_loan_balance",
                ),
                filters=(),
                group_by=(),
            ),

            "generated_sql": (
                "SELECT "
                "SUM(loan_bal_rmb) "
                "FROM ods_hd_100_cldkxx"
            ),

            "trusted_sql": None,

            "success": False,

            "validation_status": (
                "no_issue"
            ),

            "validation_error_message": (
                None
            ),

            "semantic_validation_status": (
                "fail"
            ),

            "semantic_missing_requirements": (
                "统计期",
                "高新技术企业筛选口径",
            ),

            "semantic_issues": (
                "SQL 缺少统计期过滤条件",
                "SQL 未落实高新技术企业筛选条件",
            ),
        }


def test_result_preserves_semantic_diagnostics():
    capability = TextToSQLCapability(
        graph=FakeGraph(),
    )

    result = capability.generate(
        TextToSQLRequest(
            question=(
                "统计本期高新技术企业"
                "贷款余额"
            )
        )
    )

    assert isinstance(
        result,
        TextToSQLResult,
    )

    assert (
        result.semantic_validation_status
        == "fail"
    )

    assert (
        result.semantic_missing_requirements
        == (
            "统计期",
            "高新技术企业筛选口径",
        )
    )

    assert (
        result.semantic_issues
        == (
            "SQL 缺少统计期过滤条件",
            "SQL 未落实高新技术企业筛选条件",
        )
    )