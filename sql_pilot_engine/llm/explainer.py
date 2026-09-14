from __future__ import annotations

from typing import Any

from sql_pilot_engine.explain.context import ProductionExplainContext
from sql_pilot_engine.llm.protocols import StructuredGenerationModel
from sql_pilot_engine.llm.explain_prompts import (
    CTE_EXPLAIN_BATCH_JSON_SCHEMA,
    CTE_EXPLAIN_SYSTEM_PROMPT,
    EXPLAIN_JSON_SCHEMA,
    EXPLAIN_SYSTEM_PROMPT,
    build_cte_explain_user_prompt,
    build_explain_user_prompt,
)


class LLMExplainer:
    """
    Production Explain 的语义层。

    对复杂 SQL 不做 one-shot：
    1. 先按 CTE chunk 分批解释；
    2. 再基于 deterministic Program/Evidence + CTE 语义做程序级汇总；
    3. 对模型返回的结构身份做白名单过滤，避免语义层创造表/字段/CTE。
    """

    def __init__(
        self,
        client: StructuredGenerationModel,
        *,
        cte_batch_size: int = 6,
    ) -> None:
        if cte_batch_size <= 0:
            raise ValueError("cte_batch_size must be positive.")
        self.client = client
        self.cte_batch_size = cte_batch_size

    def explain(
        self,
        *,
        context: ProductionExplainContext,
    ) -> dict[str, Any]:
        cte_explanations = self._explain_ctes(context)
        program_payload = context.compact_program_payload()

        payload = self.client.generate_json(
            system_prompt=EXPLAIN_SYSTEM_PROMPT,
            user_prompt=build_explain_user_prompt(
                program_context=program_payload,
                cte_explanations=cte_explanations,
            ),
            json_schema=EXPLAIN_JSON_SCHEMA,
        )

        sanitized = self._sanitize_program_payload(
            payload=payload,
            context=context,
        )
        sanitized["cte_explanations"] = cte_explanations
        return sanitized

    def _explain_ctes(
        self,
        context: ProductionExplainContext,
    ) -> list[dict[str, Any]]:
        if not context.ctes:
            return []

        allowed = {
            (item.statement_index, item.name): item
            for item in context.ctes
        }
        explanations: list[dict[str, Any]] = []

        for start in range(0, len(context.ctes), self.cte_batch_size):
            batch = context.ctes[start : start + self.cte_batch_size]
            response = self.client.generate_json(
                system_prompt=CTE_EXPLAIN_SYSTEM_PROMPT,
                user_prompt=build_cte_explain_user_prompt(
                    cte_batch=[item.to_prompt_payload() for item in batch],
                ),
                json_schema=CTE_EXPLAIN_BATCH_JSON_SCHEMA,
            )

            raw_items = response.get("cte_explanations") or []
            if not isinstance(raw_items, list):
                continue

            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "").strip()
                try:
                    statement_index = int(raw.get("statement_index"))
                except (TypeError, ValueError):
                    continue

                key = (statement_index, name)
                deterministic = allowed.get(key)
                if deterministic is None:
                    continue

                explanations.append(
                    {
                        "statement_index": statement_index,
                        "name": name,
                        "purpose": self._optional_text(raw.get("purpose")),
                        "processing_logic": self._optional_text(
                            raw.get("processing_logic")
                        ),
                        "business_semantics": self._optional_text(
                            raw.get("business_semantics")
                        ),
                        "input_semantics": self._optional_text(
                            raw.get("input_semantics")
                        ),
                        "output_semantics": self._optional_text(
                            raw.get("output_semantics")
                        ),
                        "confidence": self._confidence(raw.get("confidence")),
                        "uncertainties": self._string_list(
                            raw.get("uncertainties")
                        ),
                    }
                )

        # One explanation per deterministic CTE identity, preserving program order.
        by_key = {
            (item["statement_index"], item["name"]): item
            for item in explanations
        }
        return [
            by_key[(item.statement_index, item.name)]
            for item in context.ctes
            if (item.statement_index, item.name) in by_key
        ]

    @classmethod
    def _sanitize_program_payload(
        cls,
        *,
        payload: dict[str, Any],
        context: ProductionExplainContext,
    ) -> dict[str, Any]:
        deterministic = context.compact_program_payload()
        allowed_statements = {
            item.statement_index
            for item in context.statements
        }
        allowed_tables = set(deterministic["program"]["read_tables"])
        allowed_tables.update(
            item["table"]
            for item in deterministic["program"]["write_targets"]
        )
        allowed_targets = {
            item["target"]
            for item in deterministic["lineage"]["columns"]
        }

        statement_explanations: list[dict[str, Any]] = []
        for item in payload.get("statement_explanations") or []:
            if not isinstance(item, dict):
                continue
            try:
                statement_index = int(item.get("statement_index"))
            except (TypeError, ValueError):
                continue
            if statement_index not in allowed_statements:
                continue
            statement_explanations.append(
                {
                    "statement_index": statement_index,
                    "purpose": cls._optional_text(item.get("purpose")),
                    "inputs": cls._string_list(item.get("inputs")),
                    "processing_flow": cls._string_list(
                        item.get("processing_flow")
                    ),
                    "write_target": cls._optional_text(
                        item.get("write_target")
                    ),
                    "partition_behavior": cls._optional_text(
                        item.get("partition_behavior")
                    ),
                    "uncertainties": cls._string_list(
                        item.get("uncertainties")
                    ),
                }
            )

        table_roles: list[dict[str, Any]] = []
        for item in payload.get("table_roles") or []:
            if not isinstance(item, dict):
                continue
            table = str(item.get("table") or "").strip().lower()
            if table not in allowed_tables:
                continue
            table_roles.append(
                {
                    "table": table,
                    "business_role": cls._optional_text(
                        item.get("business_role")
                    ),
                    "usage_summary": cls._optional_text(
                        item.get("usage_summary")
                    ),
                    "confidence": cls._confidence(item.get("confidence")),
                    "uncertainties": cls._string_list(
                        item.get("uncertainties")
                    ),
                }
            )

        output_explanations: list[dict[str, Any]] = []
        for item in payload.get("output_column_explanations") or []:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target") or "").strip().lower()
            if target not in allowed_targets:
                continue
            output_explanations.append(
                {
                    "target": target,
                    "meaning": cls._optional_text(item.get("meaning")),
                    "derivation_summary": cls._optional_text(
                        item.get("derivation_summary")
                    ),
                    "confidence": cls._confidence(item.get("confidence")),
                    "uncertainties": cls._string_list(
                        item.get("uncertainties")
                    ),
                }
            )

        key_transformations = [
            cls._sanitize_transformation(item)
            for item in (payload.get("key_transformations") or [])
            if isinstance(item, dict)
        ]

        suspicious_points = [
            item
            for item in (payload.get("suspicious_points") or [])
            if isinstance(item, dict)
        ]

        route_signals = payload.get("route_signals")
        if not isinstance(route_signals, dict):
            route_signals = {}

        return {
            "sql_summary": str(payload.get("sql_summary") or "").strip(),
            "business_purpose": cls._optional_text(
                payload.get("business_purpose")
            ),
            "statement_explanations": statement_explanations,
            "table_roles": table_roles,
            "output_column_explanations": output_explanations,
            "key_transformations": key_transformations,
            "suspicious_points": suspicious_points,
            "uncertainties": cls._string_list(payload.get("uncertainties")),
            "route_signals": route_signals,
        }

    @classmethod
    def _sanitize_transformation(cls, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "location": cls._optional_text(item.get("location")),
            "type": cls._optional_text(item.get("type")),
            "description": cls._optional_text(item.get("description")),
            "business_impact": cls._optional_text(item.get("business_impact")),
            "confidence": cls._confidence(item.get("confidence")),
        }

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return [
            text
            for item in value
            if (text := str(item).strip())
        ]

    @staticmethod
    def _confidence(value: Any) -> float | None:
        if value is None:
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, confidence))
