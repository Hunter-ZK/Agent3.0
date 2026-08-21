from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
    QueryContextBuilder,
)
from sql_pilot_engine.generation.prompts import (
    build_planner_prompt,
    render_query_context,
)


SEMANTIC_CONTEXT = (
    "TABLE dwd_hd_101_cldwdk\n"
    "loan_bal_rmb: 贷款余额\n"
    "dt: 统计期"
)


def test_query_context_builder_preserves_session_context():
    session_context = (
        "User clarification: "
        "dt格式为yyyyMM；"
        "同比与去年同期比较；"
        "环比与上月比较。",
    )

    builder = QueryContextBuilder()

    context = builder.build(
        question="统计高新技术企业贷款余额同比及环比情况",
        semantic_context=SEMANTIC_CONTEXT,
        business_knowledge=[],
        verified_sql=[],
        session_context=session_context,
    )

    assert context.session_context == session_context
    assert context.semantic_context == SEMANTIC_CONTEXT


def test_render_query_context_includes_session_context():
    context = QueryContext(
        question="统计高新技术企业贷款余额同比及环比情况",
        semantic_context=SEMANTIC_CONTEXT,
        business_knowledge=(),
        verified_sql=(),
        session_context=(
            "User clarification: "
            "dt格式为yyyyMM；"
            "同比与去年同期比较；"
            "环比与上月比较。",
        ),
    )

    rendered = render_query_context(context)

    assert "## Session Context" in rendered
    assert "dt格式为yyyyMM" in rendered
    assert "同比与去年同期比较" in rendered
    assert "环比与上月比较" in rendered


def test_planner_prompt_contains_task_context():
    original_question = "统计高新技术企业的贷款余额同比及环比情况"

    context = QueryContext(
        question=original_question,
        semantic_context=SEMANTIC_CONTEXT,
        business_knowledge=(),
        verified_sql=(),
        session_context=(
            "User clarification: "
            "当前统计期使用${p_month_yyyymm}；"
            "dt格式为yyyyMM；"
            "同比与去年同期比较；"
            "环比与上月比较；"
            "同比和环比都计算增长率。",
        ),
    )

    prompt = build_planner_prompt(
        query_context=context,
    )

    assert original_question in prompt
    assert SEMANTIC_CONTEXT in prompt
    assert "## Session Context" in prompt
    assert "当前统计期使用${p_month_yyyymm}" in prompt
    assert "同比和环比都计算增长率" in prompt
