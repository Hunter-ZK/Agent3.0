from __future__ import annotations

import json
from typing import Any

from sql_pilot_engine.llm.protocols import StructuredGenerationModel


FIX_DIAGNOSIS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnoses": {"type": "array"},
    },
    "required": ["diagnoses"],
}


FIX_DIAGNOSIS_SYSTEM_PROMPT = """
你是生产级 SQL Fix Diagnoser。

你的职责是解释 Review Issue 的根因和可修复边界，而不是直接重写 SQL。

输入包含：
- Review Issues（确定性/Metadata/LLM Review 的结构化问题）；
- SQL Analysis；
- Program / Metadata / Lineage / Hint Evidence；
- 每个 Issue 对应的局部源码窗口。

强约束：
1. rule_id 必须来自输入 Review Issues，不得创造新问题；
2. diagnosis_status 只能是 confirmed / plausible / insufficient_context；
3. 只有当前证据足够定位且修复不需要猜业务口径时，auto_fix_safe 才能为 true；
4. 不得因为模型判断把 Review Issue 的 action 从 HUMAN_REVIEW / CONTEXT_REQUIRED 升级成自动可信；
5. Metadata、业务口径、唯一键、日期、分区语义不确定时，必须列入 required_context；
6. proposed_fix 描述最小必要修改，不输出完整 SQL；
7. 只返回 JSON object。
""".strip()


def build_fix_diagnosis_prompt(
    *,
    issues: list[dict[str, Any]],
    original_sql: str,
    analysis_context_text: str,
    metadata_context_text: str,
    program_evidence_context_text: str,
) -> str:
    issue_payload = []
    for issue in issues:
        issue_payload.append(
            {
                "rule_id": issue.get("rule_id"),
                "title": issue.get("title"),
                "severity": issue.get("severity"),
                "action": issue.get("action"),
                "message": issue.get("message"),
                "suggestion": issue.get("suggestion"),
                "evidence": issue.get("evidence"),
                "location": issue.get("location"),
                "missing_context": issue.get("missing_context") or [],
                "auto_fixable": bool(issue.get("auto_fixable", False)),
                "source_window": _issue_source_window(
                    original_sql,
                    evidence=str(issue.get("evidence") or ""),
                    location=str(issue.get("location") or ""),
                ),
            }
        )

    return f"""
## Review Issues + Local Source Windows

```json
{json.dumps(issue_payload, ensure_ascii=False, indent=2)}
```

## SQL Analysis

{analysis_context_text}

## Program / Evidence Context

{program_evidence_context_text or '无可用 Program/Evidence Context。'}

## Metadata Context

{metadata_context_text}

请针对每个输入 Issue 返回一条 diagnosis。每条建议包含：
- rule_id
- diagnosis_status
- location
- root_cause
- impact
- proposed_fix
- confidence（0~1）
- auto_fix_safe
- required_context（字符串数组）

如果无法从证据确认根因，使用 insufficient_context，不要猜。
""".strip()


class LLMFixDiagnoser:
    def __init__(self, client: StructuredGenerationModel) -> None:
        self.client = client

    def diagnose(
        self,
        *,
        issues: list[dict[str, Any]],
        original_sql: str,
        analysis_context_text: str,
        metadata_context_text: str,
        program_evidence_context_text: str,
    ) -> list[dict[str, Any]]:
        if not issues:
            return []

        raw = self.client.generate_json(
            system_prompt=FIX_DIAGNOSIS_SYSTEM_PROMPT,
            user_prompt=build_fix_diagnosis_prompt(
                issues=issues,
                original_sql=original_sql,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
                program_evidence_context_text=program_evidence_context_text,
            ),
            json_schema=FIX_DIAGNOSIS_JSON_SCHEMA,
        )
        if not isinstance(raw, dict):
            return []
        items = raw.get("diagnoses")
        if not isinstance(items, list):
            return []

        allowed = {
            str(item.get("rule_id") or "")
            for item in issues
            if item.get("rule_id")
        }
        result: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                continue
            rule_id = str(item.get("rule_id") or "").strip()
            if not rule_id or rule_id not in allowed or rule_id in seen:
                continue
            seen.add(rule_id)

            status = str(item.get("diagnosis_status") or "").strip().lower()
            if status not in {"confirmed", "plausible", "insufficient_context"}:
                status = "insufficient_context"

            confidence = _confidence(item.get("confidence"))
            auto_fix_safe = bool(item.get("auto_fix_safe", False))
            if status != "confirmed" or confidence is None or confidence < 0.8:
                auto_fix_safe = False

            result.append(
                {
                    "rule_id": rule_id,
                    "diagnosis_status": status,
                    "location": _optional_text(item.get("location")),
                    "root_cause": _optional_text(item.get("root_cause")),
                    "impact": _optional_text(item.get("impact")),
                    "proposed_fix": _optional_text(item.get("proposed_fix")),
                    "confidence": confidence,
                    "auto_fix_safe": auto_fix_safe,
                    "required_context": _string_list(item.get("required_context")),
                }
            )

        return result


def render_fix_diagnoses(diagnoses: list[dict[str, Any]]) -> str:
    if not diagnoses:
        return "无结构化 Fix Diagnosis。"
    return json.dumps(diagnoses, ensure_ascii=False, indent=2)


def _issue_source_window(
    sql: str,
    *,
    evidence: str,
    location: str,
    radius: int = 900,
) -> str:
    for needle in (evidence.strip(), location.strip()):
        if not needle:
            continue
        index = sql.find(needle)
        if index >= 0:
            start = max(0, index - radius)
            end = min(len(sql), index + len(needle) + radius)
            return sql[start:end]

    # 没有稳定锚点时只给受控头尾窗口，不把整份生产 SQL 重复塞入 Diagnosis。
    if len(sql) <= radius * 2:
        return sql
    return sql[:radius] + "\n-- [DIAGNOSIS WINDOW GAP] --\n" + sql[-radius:]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [text for item in value if (text := str(item).strip())]


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))
