from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
    QueryContextBuilder,
)
from sql_pilot_engine.generation.prompts import (
    build_planner_prompt,
    render_query_context,
)


# ============================================================
# Test 1
# QueryContextBuilder 是否真正保存 Session Context
# ============================================================


def test_query_context_builder_preserves_session_context():
    session_context = (
        (
            "User clarification: "
            "dt格式为yyyyMM；"
            "同比与去年同期比较；"
            "环比与上月比较。"
        ),
    )

    builder = QueryContextBuilder()

    context = builder.build(
        question=(
            "统计高新技术企业"
            "贷款余额同比及环比情况"
        ),
        business_knowledge=[],
        verified_sql=[],
        session_context=session_context,
    )

    assert (
        context.session_context
        == session_context
    )


# ============================================================
# Test 2
# render_query_context 是否真正渲染 Session Context
# ============================================================


def test_render_query_context_includes_session_context():
    context = QueryContext(
        question=(
            "统计高新技术企业"
            "贷款余额同比及环比情况"
        ),

        business_knowledge=(),

        verified_sql=(),

        session_context=(
            (
                "User clarification: "
                "dt格式为yyyyMM；"
                "同比与去年同期比较；"
                "环比与上月比较。"
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


# ============================================================
# Test 3
# 最终 Planner Prompt 是否真正包含 Session Context
# ============================================================


def test_planner_prompt_contains_session_context():
    original_question = (
        "统计高新技术企业的"
        "贷款余额同比及环比情况"
    )

    context = QueryContext(
        question=original_question,

        business_knowledge=(),

        verified_sql=(),

        session_context=(
            (
                "User clarification: "
                "当前统计期使用${p_month_yyyymm}；"
                "dt格式为yyyyMM；"
                "同比与去年同期比较；"
                "环比与上月比较；"
                "同比和环比都计算增长率。"
            ),
        ),
    )

    prompt = build_planner_prompt(
        question=original_question,

        semantic_context=(
            "TABLE dwd_hd_101_cldwdk\n"
            "loan_bal_rmb: 贷款余额\n"
            "dt: 统计期"
        ),

        query_context=context,
    )

    # 原始问题不能丢。
    assert (
        original_question
        in prompt
    )

    # Session Context 标题必须存在。
    assert (
        "## Session Context"
        in prompt
    )

    # 用户第一轮补充必须真实进入最终 Prompt。
    assert (
        "当前统计期使用${p_month_yyyymm}"
        in prompt
    )

    assert (
        "dt格式为yyyyMM"
        in prompt
    )

    assert (
        "同比与去年同期比较"
        in prompt
    )

    assert (
        "环比与上月比较"
        in prompt
    )

    assert (
        "同比和环比都计算增长率"
        in prompt
    )