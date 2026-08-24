from __future__ import annotations


import argparse


from dataclasses import dataclass

from text_to_sql_demo import (
    build_demo_service,
)

from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLResult,
)


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    question: str

    # result / clarification
    expected_initial: str

    expected_table: str | None = None
    expected_metric: str | None = None

    # 需要 HITL 时自动回答
    clarification_answer: str | None = None


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    passed: bool

    initial_behavior: str

    final_success: bool | None
    validation_status: str | None
    validation_error: str | None
    
    semantic_status: str | None

    trusted_sql: str | None

    reason: str


CASES = (
    # ========================================================
    # 1. 明确业务 + 明确月份
    # ========================================================
    EvalCase(
        case_id="explicit_high_tech_month",
        question=(
            "统计2026年7月"
            "高新技术企业的贷款余额"
        ),
        expected_initial="result",
        expected_table=(
            "ods_hd_100_cldkxx"
        ),
        expected_metric=(
            "tech_loan_balance"
        ),
    ),

    # ========================================================
    # 2. “本期”允许使用运行参数
    # ========================================================
    EvalCase(
        case_id="current_high_tech",
        question=(
            "统计本期高新技术企业的"
            "贷款余额"
        ),
        expected_initial="result",
        expected_table=(
            "ods_hd_100_cldkxx"
        ),
        expected_metric=(
            "tech_loan_balance"
        ),
    ),

    # ========================================================
    # 3. 同比允许基于本期参数推导
    # ========================================================
    EvalCase(
        case_id="high_tech_yoy",
        question=(
            "统计高新技术企业贷款余额同比"
        ),
        expected_initial="result",
        expected_table=(
            "ods_hd_100_cldkxx"
        ),
        expected_metric=(
            "tech_loan_balance"
        ),
    ),

    # ========================================================
    # 4. 业务主题歧义 → Clarification
    #    回答后必须成功 Resume
    # ========================================================
    EvalCase(
        case_id="ambiguous_current_loan",
        question=(
            "统计本期贷款余额"
        ),
        expected_initial="clarification",
        clarification_answer=(
            "绿色贷款"
        ),
        expected_table=(
            "ods_hd_200_cldkxx"
        ),
        expected_metric=(
            "green_loan_balance"
        ),
    ),

    # ========================================================
    # 5. 明确绿色贷款
    # ========================================================
    EvalCase(
        case_id="explicit_green_current",
        question=(
            "统计本期绿色贷款余额"
        ),
        expected_initial="result",
        expected_table=(
            "ods_hd_200_cldkxx"
        ),
        expected_metric=(
            "green_loan_balance"
        ),
    ),

    # ========================================================
    # 6. 没有“本期”也仍存在业务主题歧义
    # ========================================================
    EvalCase(
        case_id="ambiguous_loan_balance",
        question=(
            "统计贷款余额"
        ),
        expected_initial="clarification",
        clarification_answer=(
            "高新技术企业贷款"
        ),
        expected_table=(
            "ods_hd_100_cldkxx"
        ),
        expected_metric=(
            "tech_loan_balance"
        ),
    ),
)


def normalize_table_name(
    value: str,
) -> str:
    return (
        value
        .strip()
        .lower()
        .split(".")[-1]
    )


def result_matches_case(
    *,
    response: TextToSQLResult,
    case: EvalCase,
) -> tuple[bool, str]:

    if not response.success:
        return (
            False,
            (
                "Text-to-SQL 最终 "
                "success=False; "
                f"validation="
                f"{response.validation_status}; "
                f"semantic="
                f"{response.semantic_validation_status}"
            ),
        )

    if not response.trusted_sql:
        return (
            False,
            "success=True 但没有 Trusted SQL。",
        )

    if (
        response.validation_status
        == "review_failed"
    ):
        return (
            False,
            "SQL Review 出现系统级失败。",
        )

    if (
        response.semantic_validation_status
        not in {
            None,
            "pass",
        }
    ):
        return (
            False,
            (
                "Semantic Validation "
                "没有通过："
                f"{response.semantic_validation_status}"
            ),
        )

    if case.expected_table is not None:
        actual_tables = {
            normalize_table_name(table)
            for table
            in response.query_plan.tables
        }

        expected_table = (
            normalize_table_name(
                case.expected_table
            )
        )

        if (
            expected_table
            not in actual_tables
        ):
            return (
                False,
                (
                    "QueryPlan 表选择错误："
                    f"expected={expected_table}, "
                    f"actual={sorted(actual_tables)}"
                ),
            )

    if case.expected_metric is not None:
        if (
            case.expected_metric
            not in response.query_plan.metrics
        ):
            return (
                False,
                (
                    "QueryPlan metric 错误："
                    f"expected="
                    f"{case.expected_metric}, "
                    f"actual="
                    f"{response.query_plan.metrics}"
                ),
            )

    return (
        True,
        "Trusted SQL 路径通过。",
    )


def evaluate_case(
    *,
    service,
    case: EvalCase,
) -> EvalResult:

    try:
        response = service.generate(
            request=__import__(
                "sql_pilot_engine.schemas.text_to_sql",
                fromlist=[
                    "TextToSQLRequest"
                ],
            ).TextToSQLRequest(
                question=case.question,
                dialect="maxcompute",
            )
        )

    except Exception as error:
        return EvalResult(
            case_id=case.case_id,
            passed=False,
            initial_behavior="exception",
            final_success=None,
            validation_status=None,
            validation_error=(
                getattr(
                    response,
                    "validation_error_message",
                    None,
                )
            ),
            semantic_status=None,
            trusted_sql=None,
            reason=(
                "系统异常："
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

    # ========================================================
    # 初始应当 Clarification
    # ========================================================

    if (
        case.expected_initial
        == "clarification"
    ):
        if not isinstance(
            response,
            TextToSQLClarification,
        ):
            return EvalResult(
                case_id=case.case_id,
                passed=False,
                initial_behavior="result",
                final_success=(
                    getattr(
                        response,
                        "success",
                        None,
                    )
                ),
                validation_status=(
                    getattr(
                        response,
                        "validation_status",
                        None,
                    )
                ),
                validation_error=(
                    getattr(
                        response,
                        "validation_error_message",
                        None,
                    )
                ),
                semantic_status=(
                    getattr(
                        response,
                        "semantic_validation_status",
                        None,
                    )
                ),
                trusted_sql=(
                    getattr(
                        response,
                        "trusted_sql",
                        None,
                    )
                ),
                reason=(
                    "预期 Clarification，"
                    "但系统直接给出了最终结果。"
                ),
            )

        if not case.clarification_answer:
            return EvalResult(
                case_id=case.case_id,
                passed=True,
                initial_behavior="clarification",
                final_success=None,
                validation_status=None,
                validation_error=(
                    getattr(
                        response,
                        "validation_error_message",
                        None,
                    )
                ),
                semantic_status=None,
                trusted_sql=None,
                reason=(
                    "Clarification 行为符合预期。"
                ),
            )

        if not response.thread_id:
            return EvalResult(
                case_id=case.case_id,
                passed=False,
                initial_behavior="clarification",
                final_success=None,
                validation_status=None,
                validation_error=(
                    getattr(
                        response,
                        "validation_error_message",
                        None,
                    )
                ),
                semantic_status=None,
                trusted_sql=None,
                reason=(
                    "Clarification 缺少 thread_id，"
                    "无法 Resume。"
                ),
            )

        try:
            response = service.resume(
                thread_id=response.thread_id,
                answer=(
                    case.clarification_answer
                ),
            )

        except Exception as error:
            return EvalResult(
                case_id=case.case_id,
                passed=False,
                initial_behavior="clarification",
                final_success=None,
                validation_status=None,
                validation_error=(
                    getattr(
                        response,
                        "validation_error_message",
                        None,
                    )
                ),
                semantic_status=None,
                trusted_sql=None,
                reason=(
                    "Resume 系统异常："
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

        if isinstance(
            response,
            TextToSQLClarification,
        ):
            return EvalResult(
                case_id=case.case_id,
                passed=False,
                initial_behavior="clarification",
                final_success=None,
                validation_status=None,
                validation_error=(
                    getattr(
                        response,
                        "validation_error_message",
                        None,
                    )
                ),
                semantic_status=None,
                trusted_sql=None,
                reason=(
                    "有效补充后仍再次要求 "
                    "Clarification。"
                ),
            )

        passed, reason = (
            result_matches_case(
                response=response,
                case=case,
            )
        )

        return EvalResult(
            case_id=case.case_id,
            passed=passed,
            initial_behavior="clarification",
            final_success=response.success,
            validation_status=(
                response.validation_status
            ),
            validation_error=(
                getattr(
                    response,
                    "validation_error_message",
                    None,
                )
            ),
            semantic_status=(
                response
                .semantic_validation_status
            ),
            trusted_sql=response.trusted_sql,
            reason=reason,
        )

    # ========================================================
    # 初始应直接得到 Result
    # ========================================================

    if isinstance(
        response,
        TextToSQLClarification,
    ):
        return EvalResult(
            case_id=case.case_id,
            passed=False,
            initial_behavior="clarification",
            final_success=None,
            validation_status=None,
            validation_error=(
                getattr(
                    response,
                    "validation_error_message",
                    None,
                )
            ),
            semantic_status=None,
            trusted_sql=None,
            reason=(
                "预期直接完成，"
                "但系统要求 Clarification："
                f"{response.clarification_question}"
            ),
        )

    passed, reason = (
        result_matches_case(
            response=response,
            case=case,
        )
    )

    return EvalResult(
        case_id=case.case_id,
        passed=passed,
        initial_behavior="result",
        final_success=response.success,
        validation_status=(
            response.validation_status
        ),
        validation_error=(
            getattr(
                response,
                "validation_error_message",
                None,
            )
        ),
        semantic_status=(
            response
            .semantic_validation_status
        ),
        trusted_sql=response.trusted_sql,
        reason=reason,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help=(
            "只运行指定 case_id；"
            "可重复传入。"
        ),
    )

    return parser.parse_args()

def main() -> None:

    args = parse_args()

    selected_cases = CASES

    if args.cases:
        selected = set(args.cases)

        selected_cases = tuple(
            case
            for case in CASES
            if case.case_id in selected
        )

    print("=" * 78)
    print(
        "Agent3.0 · Text-to-SQL "
        "Real LLM Evaluation V2"
    )
    print("=" * 78)

    service = build_demo_service(
        use_real_llm=True
    )

    results: list[EvalResult] = []

    for index, case in enumerate(
        selected_cases,
        start=1,
    ):
        print()
        print(
            f"[{index}/{len(selected_cases)}] "
            f"{case.case_id}"
        )

        print(
            "question:",
            case.question,
        )

        result = evaluate_case(
            service=service,
            case=case,
        )

        results.append(
            result
        )

        print(
            "result:",
            (
                "PASS"
                if result.passed
                else "FAIL"
            ),
        )

        print(
            "initial:",
            result.initial_behavior,
        )

        print(
            "validation:",
            result.validation_status,
        )

        print(
            "semantic:",
            result.semantic_status,
        )

        print(
            "reason:",
            result.reason,
        )

        if result.validation_error:
            print(
                "validation_error:",
                result.validation_error,
            )

    # ========================================================
    # Summary
    # ========================================================

    total = len(results)

    passed = sum(
        1
        for result in results
        if result.passed
    )

    clarification_expected = sum(
        1
        for case in selected_cases
        if (
            case.expected_initial
            == "clarification"
        )
    )

    clarification_hit = sum(
        1
        for case, result
        in zip(
            selected_cases,
            results,
            strict=True,
        )
        if (
            case.expected_initial
            == "clarification"
            and result.initial_behavior
            == "clarification"
        )
    )

    system_errors = sum(
        1
        for result in results
        if (
            result.initial_behavior
            == "exception"
            or result.validation_status
            == "review_failed"
            or "系统异常"
            in result.reason
        )
    )

    print()
    print("=" * 78)
    print("Evaluation Summary")
    print("=" * 78)

    print(
        "passed:",
        f"{passed}/{total}",
    )

    print(
        "pass_rate:",
        f"{passed / total:.1%}",
    )

    print(
        "clarification_accuracy:",
        (
            f"{clarification_hit}/"
            f"{clarification_expected}"
        ),
    )

    print(
        "system_errors:",
        system_errors,
    )

    print()

    if passed == total:
        print(
            "RESULT: REAL LLM GATE PASS"
        )
    else:
        print(
            "RESULT: REAL LLM GATE FAIL"
        )


if __name__ == "__main__":
    main()