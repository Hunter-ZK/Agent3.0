from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from sql_pilot_engine.evaluation.text_to_sql.models import (
    TextToSQLEvalResult,
)


# 报告结构一旦被外部脚本或 CI 消费，就属于可版本化的数据 Contract。
# 本轮只补充 Phase 4.1 已经进入 EvalResult 的可观测字段，不改变顶层 schema_version。
REPORT_SCHEMA_VERSION = "1"

# 这四条规则是 Phase 2.3-D 已冻结的 Evidence Advisory 规则。
# Reporter 只统计命中次数，不在报告层重新解释 IssueAction 或改变 Gate 结论。
EVIDENCE_RULE_IDS = (
    "METRIC_TABLE",
    "METRIC_AGGREGATION",
    "METRIC_FIXED_FILTER",
    "PARTITION_CONSTRAINT",
)


def _rate(passed: int, total: int) -> float:
    """统一计算比例；没有分母时返回 0.0，避免 Reporter 自己抛除零异常。"""

    if total <= 0:
        return 0.0
    return passed / total


def _failure_type_text(
    result: TextToSQLEvalResult,
) -> str | None:
    """把 Enum / string 统一投影成稳定 JSON 字符串。"""

    failure_type = result.failure_type
    if failure_type is None:
        return None

    value = getattr(
        failure_type,
        "value",
        failure_type,
    )
    return str(value)


def _result_to_dict(
    result: TextToSQLEvalResult,
) -> dict[str, object]:
    """
    把单次 Evaluation Run 投影成可持久化 JSON。

    【为什么 Phase 4.1 的三个字段必须写到 run 级结果】
    summary 中的 compile_rate 只能告诉我们“总体编译了多少”，无法解释某个失败/波动 run：
    - Compiler 是否真正被尝试；
    - 是否成功编译；
    - 为什么 fallback；
    - 最终 SQL Candidate 是 Compiler 还是 LLM 产生。

    因此 generation_source / compilation_status / compilation_fallback_reason 必须同时保留在
    每个 run 的结果里。它们是 observability，不参与 failure_type 的重新分类。
    """

    return {
        "case_id": result.case_id,
        "run_index": result.run_index,
        "initial_behavior": result.initial_behavior,
        "clarification_pass": result.clarification_pass,
        "planning_pass": result.planning_pass,
        "schema_link_pass": result.schema_link_pass,
        "generation_pass": result.generation_pass,
        "gate_pass": result.gate_pass,
        "semantic_pass": result.semantic_pass,
        "final_pass": result.final_pass,
        "system_error": result.system_error,
        "failure_type": _failure_type_text(result),
        "validation_status": result.validation_status,
        "semantic_status": result.semantic_status,
        "validation_error": result.validation_error,
        "generation_source": result.generation_source,
        "compilation_status": result.compilation_status,
        "compilation_fallback_reason": result.compilation_fallback_reason,
        "linking_failure_codes": list(
            result.linking_failure_codes
        ),
        "validation_rule_ids": list(
            result.validation_rule_ids
        ),
        "evidence_rule_hits": list(
            result.evidence_rule_hits
        ),
        "generated_sql": result.generated_sql,
        "trusted_sql": result.trusted_sql,
        "reason": result.reason,
    }


def _build_case_summaries(
    results: tuple[TextToSQLEvalResult, ...],
) -> list[dict[str, object]]:
    """
    把重复运行聚合为 case 级稳定性结果。

    stable_outcome 只表示多次运行结论一致，可能是“稳定成功”也可能是“稳定失败”；
    stable_pass 才表示该 case 的每一次 run 都 PASS。技术方案要求 repeat=5 时 5/5 才算稳定通过。
    """

    grouped: dict[
        str,
        list[TextToSQLEvalResult],
    ] = defaultdict(list)

    for result in results:
        grouped[result.case_id].append(result)

    summaries: list[dict[str, object]] = []

    for case_id in sorted(grouped):
        case_results = sorted(
            grouped[case_id],
            key=lambda item: item.run_index,
        )
        runs = len(case_results)
        pass_count = sum(
            result.final_pass
            for result in case_results
        )

        final_values = {
            result.final_pass
            for result in case_results
        }
        stable_outcome = len(final_values) == 1
        stable_pass = pass_count == runs

        failure_types = sorted(
            {
                value
                for result in case_results
                if (
                    value := _failure_type_text(result)
                )
                is not None
            }
        )

        evidence_rule_hits = sorted(
            {
                rule_id
                for result in case_results
                for rule_id in result.evidence_rule_hits
            }
        )

        summaries.append(
            {
                "case_id": case_id,
                "runs": runs,
                "pass_count": pass_count,
                "pass_rate": _rate(
                    pass_count,
                    runs,
                ),
                "stable_outcome": stable_outcome,
                "stable_pass": stable_pass,
                "failure_types": failure_types,
                "evidence_rule_hits": evidence_rule_hits,
            }
        )

    return summaries


def build_evaluation_report(
    *,
    results: tuple[TextToSQLEvalResult, ...],
    repeat: int,
) -> dict[str, object]:
    """
    构建 deterministic Text-to-SQL Evaluation V2 报告对象。

    Reporter 只聚合已经由 Evaluator 计算出的事实，不重新评分，也不擅自宣布 Phase Gate 通过。

    【compile_rate 口径】
        compiled_runs / compilation_attempts

    compilation_attempts 只统计 ``compilation_status is not None`` 的 run，也就是已经完成
    Planning + Linking 并真正到达 Compiler 的查询。Planning/Linking 之前结束的请求不进入分母。
    NOT_COMPILABLE 是正常 fallback，因此不会增加 failure_counts，只有 fallback reason 单独统计。
    """

    if not results:
        raise ValueError(
            "evaluation results must not be empty"
        )
    if repeat < 1:
        raise ValueError(
            "repeat must be >= 1"
        )

    total_runs = len(results)
    case_summaries = _build_case_summaries(
        results
    )
    total_cases = len(case_summaries)

    clarification_passes = sum(
        result.clarification_pass
        for result in results
    )
    planning_passes = sum(
        result.planning_pass
        for result in results
    )
    schema_link_passes = sum(
        result.schema_link_pass
        for result in results
    )
    generation_passes = sum(
        result.generation_pass
        for result in results
    )
    gate_passes = sum(
        result.gate_pass
        for result in results
    )
    semantic_passes = sum(
        result.semantic_pass
        for result in results
    )
    final_passes = sum(
        result.final_pass
        for result in results
    )
    system_errors = sum(
        result.system_error
        for result in results
    )

    # Phase 4.1 编译指标。这里只读取 EvalResult 的观测事实，不从 SQL 文本反推来源。
    compilation_attempts = sum(
        result.compilation_status is not None
        for result in results
    )
    compiled_runs = sum(
        result.compilation_status == "compiled"
        for result in results
    )
    compile_rate = _rate(
        compiled_runs,
        compilation_attempts,
    )

    stable_outcome_cases = sum(
        bool(item["stable_outcome"])
        for item in case_summaries
    )
    stable_pass_cases = sum(
        bool(item["stable_pass"])
        for item in case_summaries
    )
    unstable_cases = (
        total_cases - stable_outcome_cases
    )

    failure_counts = Counter(
        failure_type
        for result in results
        if (
            failure_type := _failure_type_text(result)
        )
        is not None
    )

    fallback_counts = Counter(
        result.compilation_fallback_reason
        for result in results
        if result.compilation_fallback_reason is not None
    )

    evidence_rule_hit_counts = Counter(
        rule_id
        for result in results
        for rule_id in result.evidence_rule_hits
    )

    gate_false_negative_runs = failure_counts[
        "gate_false_negative"
    ]
    gate_false_negative_cases = sum(
        1
        for item in case_summaries
        if "gate_false_negative" in item["failure_types"]
    )

    pass_with_evidence_advisory = [
        {
            "case_id": result.case_id,
            "run_index": result.run_index,
            "evidence_rule_hits": list(
                result.evidence_rule_hits
            ),
        }
        for result in results
        if result.final_pass
        and result.evidence_rule_hits
    ]

    # JSON 结果固定按 case_id / run_index 排序，保证同一输入重复生成文件时可以直接 diff。
    ordered_results = sorted(
        results,
        key=lambda item: (
            item.case_id,
            item.run_index,
        ),
    )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "evaluation": "text_to_sql_v2",
        "configuration": {
            "repeat": repeat,
            "case_count": total_cases,
            "run_count": total_runs,
        },
        "summary": {
            "clarification_rate": _rate(
                clarification_passes,
                total_runs,
            ),
            "planning_rate": _rate(
                planning_passes,
                total_runs,
            ),
            "schema_link_rate": _rate(
                schema_link_passes,
                total_runs,
            ),
            "generation_rate": _rate(
                generation_passes,
                total_runs,
            ),
            "compilation_attempts": compilation_attempts,
            "compiled_runs": compiled_runs,
            "compile_rate": compile_rate,
            "gate_rate": _rate(
                gate_passes,
                total_runs,
            ),
            "semantic_rate": _rate(
                semantic_passes,
                total_runs,
            ),
            "final_success_rate": _rate(
                final_passes,
                total_runs,
            ),
            "system_error_rate": _rate(
                system_errors,
                total_runs,
            ),
            "stable_outcome_cases": stable_outcome_cases,
            "stable_pass_cases": stable_pass_cases,
            "unstable_cases": unstable_cases,
            "stable_pass_rate": _rate(
                stable_pass_cases,
                total_cases,
            ),
            "gate_false_negative_runs": gate_false_negative_runs,
            "gate_false_negative_cases": gate_false_negative_cases,
        },
        "quality_gates": {
            # 这里只报告客观条件；“整个 Phase 是否通过”仍由 Stage Gate 决策层判断。
            "repeat_5_or_more": repeat >= 5,
            "gate_false_negative_zero": gate_false_negative_runs == 0,
        },
        "failure_counts": {
            key: failure_counts[key]
            for key in sorted(failure_counts)
        },
        "compilation_fallback_counts": {
            key: fallback_counts[key]
            for key in sorted(fallback_counts)
        },
        "evidence_rule_hit_counts": {
            rule_id: evidence_rule_hit_counts[rule_id]
            for rule_id in EVIDENCE_RULE_IDS
        },
        "pass_with_evidence_advisory": pass_with_evidence_advisory,
        "cases": case_summaries,
        "results": [
            _result_to_dict(result)
            for result in ordered_results
        ],
    }


def render_markdown_report(
    report: dict[str, object],
) -> str:
    """
    把结构化报告渲染成稳定、可读、可 Git diff 的 Markdown。

    Markdown 只做展示，不重新计算指标。所有数字都来自 build_evaluation_report()，从而保证
    JSON 与 Markdown 不会因为两套计算逻辑而出现口径不一致。
    """

    configuration = report["configuration"]
    summary = report["summary"]
    quality_gates = report["quality_gates"]
    failure_counts = report["failure_counts"]
    fallback_counts = report["compilation_fallback_counts"]
    rule_counts = report["evidence_rule_hit_counts"]
    cases = report["cases"]
    advisory_passes = report["pass_with_evidence_advisory"]

    lines: list[str] = [
        "# Text-to-SQL Evaluation V2",
        "",
        "## Configuration",
        "",
        f"- Cases: {configuration['case_count']}",
        f"- Repeat: {configuration['repeat']}",
        f"- Runs: {configuration['run_count']}",
        "",
        "## Six-Layer Summary",
        "",
        "| Layer | Rate |",
        "| --- | ---: |",
        f"| Clarification | {summary['clarification_rate']:.1%} |",
        f"| Planning | {summary['planning_rate']:.1%} |",
        f"| Schema Link | {summary['schema_link_rate']:.1%} |",
        f"| Generation | {summary['generation_rate']:.1%} |",
        f"| Gate | {summary['gate_rate']:.1%} |",
        f"| Semantic | {summary['semantic_rate']:.1%} |",
        f"| Final | {summary['final_success_rate']:.1%} |",
        f"| System Error | {summary['system_error_rate']:.1%} |",
        "",
        "## Metric Compilation",
        "",
        f"- Compilation attempts: {summary['compilation_attempts']}",
        f"- Compiled runs: {summary['compiled_runs']}",
        f"- Compile rate: {summary['compile_rate']:.1%}",
        "",
        "### Fallback Reasons",
        "",
    ]

    if fallback_counts:
        lines.extend(
            (
                "| Reason | Count |",
                "| --- | ---: |",
            )
        )
        for reason in sorted(fallback_counts):
            lines.append(
                f"| {reason} | {fallback_counts[reason]} |"
            )
    else:
        lines.append("None.")

    lines.extend(
        (
            "",
            "## Stability",
            "",
            (
                "- Stable outcome cases: "
                f"{summary['stable_outcome_cases']}/"
                f"{configuration['case_count']}"
            ),
            (
                "- Stable PASS cases: "
                f"{summary['stable_pass_cases']}/"
                f"{configuration['case_count']}"
            ),
            f"- Unstable cases: {summary['unstable_cases']}",
            f"- Stable PASS rate: {summary['stable_pass_rate']:.1%}",
            "",
            "## Redline",
            "",
            f"- GATE_FALSE_NEGATIVE runs: {summary['gate_false_negative_runs']}",
            f"- GATE_FALSE_NEGATIVE cases: {summary['gate_false_negative_cases']}",
            f"- Redline satisfied: {quality_gates['gate_false_negative_zero']}",
            "",
            "## Failure Classification",
            "",
        )
    )

    if failure_counts:
        lines.extend(
            (
                "| Failure Type | Count |",
                "| --- | ---: |",
            )
        )
        for failure_type in sorted(failure_counts):
            lines.append(
                f"| {failure_type} | {failure_counts[failure_type]} |"
            )
    else:
        lines.append("No classified failures.")

    lines.extend(
        (
            "",
            "## Evidence Rule Hits",
            "",
            "| Rule | Hits |",
            "| --- | ---: |",
        )
    )
    for rule_id in EVIDENCE_RULE_IDS:
        lines.append(
            f"| {rule_id} | {rule_counts[rule_id]} |"
        )

    lines.extend(
        (
            "",
            "## Per-Case Stability",
            "",
            "| Case | PASS | Runs | Stable Outcome | Stable PASS | Failure Types | Evidence Rules |",
            "| --- | ---: | ---: | :---: | :---: | --- | --- |",
        )
    )

    for item in cases:
        failure_text = ", ".join(item["failure_types"]) or "-"
        evidence_text = ", ".join(item["evidence_rule_hits"]) or "-"
        lines.append(
            (
                f"| {item['case_id']} "
                f"| {item['pass_count']} "
                f"| {item['runs']} "
                f"| {item['stable_outcome']} "
                f"| {item['stable_pass']} "
                f"| {failure_text} "
                f"| {evidence_text} |"
            )
        )

    lines.extend(
        (
            "",
            "## PASS with Evidence Advisories",
            "",
        )
    )

    if advisory_passes:
        for item in advisory_passes:
            rules = ", ".join(item["evidence_rule_hits"])
            lines.append(
                f"- {item['case_id']} run={item['run_index']}: {rules}"
            )
    else:
        lines.append("None.")

    lines.append("")
    return "\n".join(lines)


def write_evaluation_report(
    *,
    report: dict[str, object],
    output_dir: Path,
) -> tuple[Path, Path]:
    """
    以固定文件名写出 JSON + Markdown 报告。

    不写 timestamp、hostname、随机 ID 等机器噪音；JSON 使用 sort_keys=True，保证相同报告对象
    在不同目录写出时字节级稳定，方便 Git diff 和回归比较。
    """

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = output_dir / "evaluation.json"
    markdown_path = output_dir / "evaluation.md"

    json_text = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    json_path.write_text(
        json_text + "\n",
        encoding="utf-8",
    )

    markdown_path.write_text(
        render_markdown_report(report),
        encoding="utf-8",
    )

    return json_path, markdown_path