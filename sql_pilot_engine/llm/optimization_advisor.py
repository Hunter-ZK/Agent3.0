from __future__ import annotations

import json
from typing import Any

from sql_pilot_engine.llm.protocols import StructuredGenerationModel


OPTIMIZATION_ADVISOR_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "opportunities": {"type": "array"},
    },
    "required": ["summary", "opportunities"],
}


OPTIMIZATION_ADVISOR_SYSTEM_PROMPT = """
你是生产级 MaxCompute SQL Optimization Advisor。

你的职责是寻找“有证据的优化机会”，不是直接重写 SQL。

输入包含：
- SQL Analysis
- Program / Metadata / Lineage / Hint Evidence
- Production Explain 结果（如可用）
- Optimization goals

每个 opportunity 建议包含：
- id
- category
- location
- evidence
- description
- semantic_argument：为什么该变化可能保持业务语义
- expected_benefit：只能用定性表述
- priority：low / medium / high
- risk
- confidence：0~1
- requires_statistics
- requires_execution_validation
- rewrite_safe

强约束：
1. 没有 Statistics / Execution Plan 时，不得声称具体性能提升比例；
2. requires_statistics=true 的机会 rewrite_safe 必须为 false；
3. 涉及 JOIN 类型、粒度、指标口径、业务过滤、分区语义变化的机会默认 rewrite_safe=false；
4. Program / Evidence 中不存在的表、字段、CTE、Hint 不得创造；
5. rewrite_safe 只表示“可以进入候选改写阶段”，不表示最终可信；
6. 证据不足时保留为 suggestion，不要为了产生候选而夸大确定性；
7. 只返回 JSON object。
""".strip()


def build_optimization_advisor_prompt(
    *,
    dialect: str,
    optimization_goals: list[str],
    analysis_context_text: str,
    metadata_context_text: str,
    explain_context_text: str,
    program_evidence_context_text: str,
) -> str:
    payload = {
        "dialect": dialect,
        "optimization_goals": optimization_goals or [
            "保持业务语义不变，降低不必要扫描、中间数据量和重复计算，并改善可维护性。"
        ],
        "analysis_context": analysis_context_text,
        "program_evidence_context": program_evidence_context_text,
        "metadata_context": metadata_context_text,
        "explain_context": explain_context_text,
    }
    return (
        "请基于下列确定性上下文识别优化机会。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


class LLMOptimizationAdvisor:
    def __init__(self, client: StructuredGenerationModel) -> None:
        self.client = client

    def analyze(
        self,
        *,
        dialect: str,
        optimization_goals: list[str],
        analysis_context_text: str,
        metadata_context_text: str,
        explain_context_text: str,
        program_evidence_context_text: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        raw = self.client.generate_json(
            system_prompt=OPTIMIZATION_ADVISOR_SYSTEM_PROMPT,
            user_prompt=build_optimization_advisor_prompt(
                dialect=dialect,
                optimization_goals=optimization_goals,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                explain_context_text=explain_context_text,
                program_evidence_context_text=program_evidence_context_text,
            ),
            json_schema=OPTIMIZATION_ADVISOR_JSON_SCHEMA,
        )
        if not isinstance(raw, dict):
            return "Optimization advisor returned no usable result.", []

        summary = str(raw.get("summary") or "").strip()
        items = raw.get("opportunities")
        if not isinstance(items, list):
            return summary, []

        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            opportunity_id = str(item.get("id") or f"opportunity_{index}").strip()
            if not opportunity_id or opportunity_id in seen:
                continue
            seen.add(opportunity_id)

            priority = str(item.get("priority") or "medium").strip().lower()
            if priority not in {"low", "medium", "high"}:
                priority = "medium"
            confidence = _confidence(item.get("confidence"))
            requires_statistics = bool(item.get("requires_statistics", False))
            requires_execution = bool(
                item.get("requires_execution_validation", False)
            )
            rewrite_safe = bool(item.get("rewrite_safe", False))
            if requires_statistics or confidence is None or confidence < 0.85:
                rewrite_safe = False

            category = str(item.get("category") or "general").strip().lower()
            if category in {
                "join_type_change",
                "grain_change",
                "metric_definition_change",
                "business_filter_change",
                "partition_semantics_change",
            }:
                rewrite_safe = False

            result.append(
                {
                    "id": opportunity_id,
                    "category": category,
                    "location": _optional_text(item.get("location")),
                    "evidence": _optional_text(item.get("evidence")),
                    "description": _optional_text(item.get("description")),
                    "semantic_argument": _optional_text(
                        item.get("semantic_argument")
                    ),
                    "expected_benefit": _optional_text(
                        item.get("expected_benefit")
                    ),
                    "priority": priority,
                    "risk": _optional_text(item.get("risk")),
                    "confidence": confidence,
                    "requires_statistics": requires_statistics,
                    "requires_execution_validation": requires_execution,
                    "rewrite_safe": rewrite_safe,
                }
            )

        return summary, result


def render_optimization_opportunities(
    opportunities: list[dict[str, Any]],
) -> str:
    return json.dumps(opportunities, ensure_ascii=False, indent=2)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))
