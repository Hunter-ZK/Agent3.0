from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.generation.models import (
    PlanningClarification,
)
from sql_pilot_engine.generation.planner import (
    QueryPlanner,
)


class AmbiguousLoanPlannerModel:
    """模拟LLM正确识别多个业务候选。"""

    def generate(
        self,
        prompt: str,
    ) -> str:
        return """
        {
          "status": "need_clarification",
          "clarification_question":
            "请确认需要统计科技贷款余额还是绿色贷款余额？",
          "missing_context": [
            "贷款业务主题"
          ],
          "reason":
            "当前Semantic Model中同时存在科技贷款余额和绿色贷款余额，用户问题未明确业务主题。"
        }
        """


def test_planner_can_clarify_ambiguous_business_subject():
    planner = QueryPlanner(
        model=AmbiguousLoanPlannerModel()
    )

    context = QueryContext(
        question=(
            "统计本期贷款余额"
        ),
        business_knowledge=(),
        verified_sql=(),
        session_context=(),
    )

    result = planner.plan(
        question=(
            "统计本期贷款余额"
        ),

        semantic_context=(
            "TABLE dwd_hd_101_cldwdk\n"
            "METRIC tech_loan_balance "
            "synonyms=贷款余额\n\n"
            "TABLE dwd_hd_201_cldwdk\n"
            "METRIC green_loan_balance "
            "synonyms=贷款余额"
        ),

        query_context=context,
    )

    assert isinstance(
        result,
        PlanningClarification,
    )

    assert result.missing_context == (
        "贷款业务主题",
    )

    assert (
        "科技贷款余额"
        in result.clarification_question
    )

    assert (
        "绿色贷款余额"
        in result.clarification_question
    )
    
from sql_pilot_engine.generation.models import (
    QueryPlan,
)


class ResolvedLoanPlannerModel:
    """模拟Session Context已经消除歧义后的Planner。"""

    def generate(
        self,
        prompt: str,
    ) -> str:
        assert (
            "当前任务讨论绿色贷款"
            in prompt
        )

        return """
        {
          "status": "ready",
          "plan": {
            "tables": [
              "dwd_hd_201_cldwdk"
            ],
            "dimensions": [],
            "metrics": [
              "green_loan_balance"
            ],
            "filters": [
              "dt = '${p_month_yyyymm}'"
            ],
            "group_by": [],
            "requirements": []
          }
        }
        """


def test_session_context_can_resolve_business_ambiguity():
    planner = QueryPlanner(
        model=ResolvedLoanPlannerModel()
    )

    context = QueryContext(
        question=(
            "统计本期贷款余额"
        ),

        business_knowledge=(),

        verified_sql=(),

        session_context=(
            (
                "User clarification: "
                "当前任务讨论绿色贷款。"
            ),
        ),
    )

    result = planner.plan(
        question=(
            "统计本期贷款余额"
        ),

        semantic_context=(
            "TABLE dwd_hd_101_cldwdk\n"
            "METRIC tech_loan_balance\n\n"
            "TABLE dwd_hd_201_cldwdk\n"
            "METRIC green_loan_balance"
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

    assert result.metrics == (
        "green_loan_balance",
    )