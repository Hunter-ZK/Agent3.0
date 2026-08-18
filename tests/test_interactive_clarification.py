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
from sql_pilot_engine.generation.prompts import (
    render_query_context,
)


class NeedClarificationModel:
    """固定模拟 Planner 判断上下文不足。"""

    def generate(
        self,
        prompt: str,
    ) -> str:
        return """
        {
          "status": "need_clarification",
          "clarification_question":
            "请说明同比和环比的时间口径。",
          "missing_context": [
            "同比时间口径",
            "环比时间口径"
          ],
          "reason":
            "当前上下文不足以可靠生成SQL。"
        }
        """


def test_planner_can_request_clarification():
    planner = QueryPlanner(
        model=NeedClarificationModel()
    )

    context = QueryContext(
        question=(
            "统计高新技术企业贷款余额"
            "同比及环比情况"
        ),
        business_knowledge=(),
        verified_sql=(),
        session_context=(),
    )

    result = planner.plan(
        question=(
            "统计高新技术企业贷款余额"
            "同比及环比情况"
        ),
        semantic_context=(
            "TABLE dwd_hd_101_cldwdk"
        ),
        query_context=context,
    )

    assert isinstance(
        result,
        PlanningClarification,
    )

    assert (
        result.clarification_question
        == "请说明同比和环比的时间口径。"
    )

    assert result.missing_context == (
        "同比时间口径",
        "环比时间口径",
    )

    assert (
        result.reason
        == "当前上下文不足以可靠生成SQL。"
    )


def test_session_context_is_rendered():
    context = QueryContext(
        question=(
            "统计高新技术企业贷款余额"
            "同比及环比情况"
        ),
        business_knowledge=(),
        verified_sql=(),
        session_context=(
            (
                "User clarification: "
                "dt格式为yyyyMM；"
                "同比与去年同期比较；"
                "环比与上月比较；"
                "同比和环比都计算增长率。"
            ),
        ),
    )

    rendered = render_query_context(
        context
    )

    assert (
        "## Session Context"
        in rendered
    )

    assert (
        "dt格式为yyyyMM"
        in rendered
    )

    assert (
        "同比与去年同期比较"
        in rendered
    )

    assert (
        "环比与上月比较"
        in rendered
    )

    assert (
        "同比和环比都计算增长率"
        in rendered
    )