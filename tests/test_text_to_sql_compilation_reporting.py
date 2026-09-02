from __future__ import annotations

from sql_pilot_engine.evaluation.text_to_sql.models import (
    TextToSQLEvalResult,
)
from sql_pilot_engine.evaluation.text_to_sql.reporting import (
    build_evaluation_report,
    render_markdown_report,
)


def _compiled_result() -> TextToSQLEvalResult:
    """
    构造一个“确定性编译成功并最终 PASS”的最小 Evaluation Run。

    这里不调用真实 Runtime，因为本测试只验证 Reporter 是否忠实保存 Evaluator 已经产生的
    Phase 4.1 observability。Compiler 算法与 Runtime routing 已由其它测试分别覆盖。
    """

    return TextToSQLEvalResult(
        case_id="compiled_case",
        run_index=1,
        initial_behavior="result",
        clarification_pass=True,
        planning_pass=True,
        schema_link_pass=True,
        generation_pass=True,
        gate_pass=True,
        semantic_pass=True,
        final_pass=True,
        system_error=False,
        failure_type=None,
        validation_status="no_issue",
        semantic_status="pass",
        validation_error=None,
        generated_sql="SELECT SUM(value) FROM table_a",
        trusted_sql="SELECT SUM(value) FROM table_a",
        reason="test",
        generation_source="compiled",
        compilation_status="compiled",
        compilation_fallback_reason=None,
    )


def _fallback_result() -> TextToSQLEvalResult:
    """
    构造一个“Compiler 正常 fallback，随后 LLM 成功”的 Run。

    这个 Case 特别用于保护一个重要语义：NOT_COMPILABLE 不是失败。
    最终 SQL 来自 LLM 时 final_pass 仍然可以为 True，只需单独记录 fallback reason。
    """

    return TextToSQLEvalResult(
        case_id="fallback_case",
        run_index=1,
        initial_behavior="result",
        clarification_pass=True,
        planning_pass=True,
        schema_link_pass=True,
        generation_pass=True,
        gate_pass=True,
        semantic_pass=True,
        final_pass=True,
        system_error=False,
        failure_type=None,
        validation_status="no_issue",
        semantic_status="pass",
        validation_error=None,
        generated_sql="SELECT complex_metric FROM table_a",
        trusted_sql="SELECT complex_metric FROM table_a",
        reason="test",
        generation_source="llm",
        compilation_status="not_compilable",
        compilation_fallback_reason="complex_expression",
    )


def test_report_serializes_per_run_compilation_observability():
    """
    summary 指标之外，每个 run 也必须保留 generation/compilation 路径。

    否则遇到同一 Case 重复 5 次只有某一次走 LLM 时，只看 compile_rate 无法定位是哪一轮发生
    fallback，也无法和 generated_sql / validation issues 做逐 run 对照。
    """

    report = build_evaluation_report(
        results=(
            _compiled_result(),
            _fallback_result(),
        ),
        repeat=1,
    )

    results = {
        item["case_id"]: item
        for item in report["results"]
    }

    compiled = results["compiled_case"]
    assert compiled["generation_source"] == "compiled"
    assert compiled["compilation_status"] == "compiled"
    assert compiled["compilation_fallback_reason"] is None

    fallback = results["fallback_case"]
    assert fallback["generation_source"] == "llm"
    assert fallback["compilation_status"] == "not_compilable"
    assert (
        fallback["compilation_fallback_reason"]
        == "complex_expression"
    )


def test_compile_rate_counts_only_runs_that_reached_compiler():
    """
    compile_rate 的冻结口径是 compiled_runs / compilation_attempts。

    两个 Run 都到达 Compiler，其中一个成功、一个正常 fallback，因此期望 1 / 2 = 50%。
    fallback Run 最终 PASS，不应进入 failure_counts。
    """

    report = build_evaluation_report(
        results=(
            _compiled_result(),
            _fallback_result(),
        ),
        repeat=1,
    )

    summary = report["summary"]
    assert summary["compilation_attempts"] == 2
    assert summary["compiled_runs"] == 1
    assert summary["compile_rate"] == 0.5
    assert report["failure_counts"] == {}
    assert (
        report["compilation_fallback_counts"]
        == {"complex_expression": 1}
    )


def test_markdown_exposes_metric_compilation_section():
    """Markdown 报告必须能直接看到编译率和 fallback 原因，而不要求人工打开 JSON。"""

    report = build_evaluation_report(
        results=(
            _compiled_result(),
            _fallback_result(),
        ),
        repeat=1,
    )

    markdown = render_markdown_report(
        report
    )

    assert "Metric Compilation" in markdown
    assert "Compile rate: 50.0%" in markdown
    assert "complex_expression" in markdown