from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


# Evaluation 首先记录“第一次运行到底返回了结果还是澄清”。
# 这是 Agent 行为观测，不等同于 planning/gate/semantic 六层中的任何一层。
InitialBehavior = Literal[
    "result",
    "clarification",
]


class EvaluationFailureType(str, Enum):
    """
    Evaluation V2 冻结的失败七分类。

    【用途】
    Evaluation 不只统计“最终成功率”，还要定位第一类主要责任层。一个失败 run 最终只归入
    一个主分类，避免同一次失败同时被 planning/linking/generation 重复计数。

    【重要边界】
    - GATE_FALSE_NEGATIVE 是当前 Trust Gate 红线；
    - GATE_FALSE_POSITIVE 不能仅因为 Gate 拒绝就自动推断，必须有额外裁决证据；
    - ASSET_DEFECT 枚举保留在统一分类中，但当前阶段不主动开展 Semantic Asset 准确性盘点；
    - Compiler NOT_COMPILABLE 不是失败分类，只是 generation path 的正常 fallback 诊断。
    """

    ASSET_DEFECT = "asset_defect"
    PLANNING_ERROR = "planning_error"
    LINKING_ERROR = "linking_error"
    GENERATION_ERROR = "generation_error"
    GATE_FALSE_POSITIVE = "gate_false_positive"
    GATE_FALSE_NEGATIVE = "gate_false_negative"
    SYSTEM_ERROR = "system_error"


@dataclass(frozen=True)
class TextToSQLEvalCase:
    """
    一个 Text-to-SQL Golden Case 的稳定输入/期望 Contract。

    Case 只保存可以客观评分的期望，不在这里嵌入 Runtime 或模型实现细节。
    required_filter_terms 用于校验 Planning 是否保留必要过滤语义，并不要求最终 SQL 文本逐字相同。
    """

    case_id: str
    question: str
    expected_initial: InitialBehavior
    clarification_answer: str | None = None
    expected_tables: tuple[str, ...] = ()
    expected_metrics: tuple[str, ...] = ()
    expected_dimensions: tuple[str, ...] = ()
    expected_group_by: tuple[str, ...] = ()
    required_filter_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # case_id 是报告稳定 diff 的主键；空值会让重复运行与聚合失去身份。
        if not self.case_id.strip():
            raise ValueError(
                "case_id cannot be empty"
            )

        if not self.question.strip():
            raise ValueError(
                "question cannot be empty"
            )


@dataclass(frozen=True)
class TextToSQLEvalResult:
    """
    一个 Golden Case 的“一次真实运行”结果。

    【六层质量链】
        planning
          ↓
        schema_link
          ↓
        generation
          ↓
        gate
          ↓
        semantic
          ↓
        final

    clarification_pass 单独记录 Agent 是否做出了正确的澄清行为，不把它伪装成第七层。

    【Phase 4.1 编译观测】
    generation_source / compilation_status / compilation_fallback_reason 只用于回答：
    - 本轮是否到达 Compiler；
    - 是否确定性编译成功；
    - fallback 的主要原因；
    - 当前 Candidate 最终来自 Compiler 还是 LLM。

    它们不直接决定 final_pass，也不进入七类 failure_type。一个 not_compilable run 完全可以
    通过 LLM fallback 获得 final_pass=True。
    """

    case_id: str
    run_index: int
    initial_behavior: str
    clarification_pass: bool

    # Evaluation V2 的六层布尔评分。
    planning_pass: bool
    schema_link_pass: bool
    generation_pass: bool
    gate_pass: bool
    semantic_pass: bool
    final_pass: bool

    # 系统异常独立记录，避免和正常业务失败混淆。
    system_error: bool
    failure_type: EvaluationFailureType | None

    # Trust / Semantic 层原始状态，便于报告定位而不是只看布尔值。
    validation_status: str | None
    semantic_status: str | None
    validation_error: str | None

    # 同时保留 Generation Candidate 与最终 Trusted SQL，支持 diff 与误杀/漏放分析。
    generated_sql: str | None
    trusted_sql: str | None

    # 本次评分结论的可读解释，例如“all evaluation layers passed”或首个失败原因。
    reason: str

    # 当前最终 Candidate 来源：compiled / llm。
    generation_source: str | None = None

    # Compiler 尝试结果：compiled / not_compilable；没到达 Compiler 则为 None。
    compilation_status: str | None = None

    # NOT_COMPILABLE 的稳定诊断原因；它本身不是失败。
    compilation_fallback_reason: str | None = None

    # Typed Linking Failure / Trust Rule / Evidence Rule 的稳定标识，用于聚合分析。
    linking_failure_codes: tuple[str, ...] = ()
    validation_rule_ids: tuple[str, ...] = ()
    evidence_rule_hits: tuple[str, ...] = ()