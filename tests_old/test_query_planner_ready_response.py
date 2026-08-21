from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.generation.models import (
    QueryPlan,
)
from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)


class ReadyPlannerModel:
    """模拟真实LLM使用新版ready + plan协议。"""

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
            ],
            "requirements": []
          }
        }
        """


def test_ready_response_reads_nested_plan():
    planner = QueryPlanner(
        model=ReadyPlannerModel()
    )

    context = QueryContext(
        question=(
            "统计本期绿色贷款余额"
        ),
        business_knowledge=(),
        verified_sql=(),
        session_context=(),
    )

    result = planner.plan(
        question=(
            "统计本期绿色贷款余额"
        ),
        semantic_context=(
            "TABLE dwd_hd_201_cldwdk"
        ),
        query_context=context,
    )

    assert isinstance(
        result,
        QueryPlan,
    )

    assert result.tables == (
        "dwd_hd_201_cldwdk",
    )

    assert result.dimensions == (
        "dt",
    )

    assert result.metrics == (
        "green_loan_balance",
    )

    assert result.filters == (
        "dt = '${p_month_yyyymm}'",
    )

    assert result.group_by == (
        "dt",
    )