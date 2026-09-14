from __future__ import annotations

import json

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.services.explain_service import ExplainService


SQL = """
WITH base AS (
    SELECT id, amount
    FROM project_src.loan_detail
    WHERE amount > 0
),
agg AS (
    SELECT id, SUM(amount) AS total_amount
    FROM base
    GROUP BY id
)
INSERT OVERWRITE TABLE project_dwd.loan_summary
SELECT id, total_amount
FROM agg
;
"""


class _SemanticExplainerModel:
    def __init__(self) -> None:
        self.calls = 0
        self.user_prompts: list[str] = []

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = system_prompt
        self.calls += 1
        self.user_prompts.append(user_prompt)
        required = set(json_schema.get("required", []))

        if "cte_explanations" in required:
            batch = _extract_first_json_block(user_prompt)
            return {
                "cte_explanations": [
                    {
                        "statement_index": item["statement_index"],
                        "name": item["name"],
                        "purpose": f"解释 {item['name']}",
                        "processing_logic": "根据局部 SQL 进行过滤/聚合",
                        "business_semantics": "贷款加工步骤",
                        "input_semantics": "上游贷款数据",
                        "output_semantics": "下游可继续加工的数据",
                        "confidence": 0.85,
                        "uncertainties": [],
                    }
                    for item in batch
                ]
            }

        return {
            "sql_summary": "汇总贷款明细并写入贷款汇总表。",
            "business_purpose": "形成贷款客户维度的金额汇总结果。",
            "statement_explanations": [
                {
                    "statement_index": 0,
                    "purpose": "生成贷款汇总结果",
                    "inputs": ["project_src.loan_detail"],
                    "processing_flow": ["过滤非正金额", "按 id 汇总金额"],
                    "write_target": "project_dwd.loan_summary",
                    "partition_behavior": None,
                    "uncertainties": [],
                },
                # Must be removed because it is not a deterministic statement.
                {
                    "statement_index": 999,
                    "purpose": "hallucinated",
                },
            ],
            "table_roles": [
                {
                    "table": "project_src.loan_detail",
                    "business_role": "贷款明细来源",
                    "usage_summary": "提供 id 和 amount",
                    "confidence": 0.9,
                    "uncertainties": [],
                },
                {
                    "table": "hallucinated.table",
                    "business_role": "不存在",
                    "usage_summary": "不存在",
                    "confidence": 1.0,
                    "uncertainties": [],
                },
            ],
            "output_column_explanations": [],
            "key_transformations": [
                {
                    "location": "agg",
                    "type": "aggregation",
                    "description": "按 id 汇总 amount",
                    "business_impact": "形成汇总金额",
                    "confidence": 0.9,
                }
            ],
            "suspicious_points": [
                {
                    "type": "semantic_review",
                    "message": "请确认 amount > 0 是否属于正式业务口径",
                }
            ],
            "uncertainties": ["未提供权威业务 Metadata"],
            "route_signals": {
                "need_metadata": True,
                "need_review": True,
                "need_human_confirm": True,
            },
        }


class _FailingModel(_SemanticExplainerModel):
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        required = set(json_schema.get("required", []))
        if "cte_explanations" in required:
            return super().generate_json(
                system_prompt,
                user_prompt,
                json_schema,
            )
        raise RuntimeError("synthetic provider timeout")


def _extract_first_json_block(prompt: str) -> list[dict]:
    body = prompt.split("```json", 1)[1].split("```", 1)[0]
    value = json.loads(body)
    assert isinstance(value, list)
    return value


def _chained_sql(cte_count: int) -> str:
    ctes = [
        "stage_00 AS (SELECT id, amount FROM project_src.loan_detail)"
    ]
    for index in range(1, cte_count):
        ctes.append(
            f"stage_{index:02d} AS ("
            f"SELECT id, amount FROM stage_{index - 1:02d})"
        )
    return (
        "WITH\n"
        + ",\n".join(ctes)
        + f"\nINSERT OVERWRITE TABLE project_dwd.loan_summary "
        f"SELECT id, amount FROM stage_{cte_count - 1:02d};"
    )


def test_explain_without_llm_returns_real_deterministic_flow():
    response = ExplainService().explain(SQLExecutionContext(sql=SQL))

    assert response.success is True
    assert "1 statement(s)" in response.sql_summary
    assert "2 CTE(s)" in response.sql_summary
    assert [item["name"] for item in response.cte_steps] == ["base", "agg"]

    base = response.cte_steps[0]
    assert base["physical_sources"] == ["project_src.loan_detail"]
    assert "SELECT" in base["sql_excerpt"]
    assert response.business_purpose is None

    assert any(
        edge["from"] == "project_src.loan_detail"
        and edge["to"] == "base"
        for edge in response.data_flow
    )
    assert any(
        edge["from"] == "base" and edge["to"] == "agg"
        for edge in response.data_flow
    )
    assert response.explain_quality["llm_enriched"] is False


def test_llm_explain_is_multi_stage_and_cannot_override_structure():
    model = _SemanticExplainerModel()
    response = ExplainService(llm_client=model).explain(
        SQLExecutionContext(sql=SQL, enable_llm=True)
    )

    assert response.success is True
    assert model.calls == 2  # one CTE batch + one program synthesis
    assert response.sql_summary == "汇总贷款明细并写入贷款汇总表。"
    assert response.business_purpose == "形成贷款客户维度的金额汇总结果。"

    assert [item["purpose"] for item in response.cte_steps] == [
        "解释 base",
        "解释 agg",
    ]
    assert response.statement_explanations[0]["purpose"] == "生成贷款汇总结果"
    assert len(response.statement_explanations) == 1

    assert {item["table"] for item in response.main_tables} == {
        "project_src.loan_detail",
        "project_dwd.loan_summary",
    }
    assert all(
        item["table"] != "hallucinated.table"
        for item in response.main_tables
    )
    assert next(
        item for item in response.main_tables
        if item["table"] == "project_src.loan_detail"
    )["business_role"] == "贷款明细来源"

    assert response.key_transformations[0]["type"] == "aggregation"
    assert response.explain_quality["llm_enriched"] is True
    assert response.explain_quality["cte_semantic_explained"] == 2
    assert response.route_signals["need_human_confirm"] is True


def test_long_program_explains_every_cte_in_bounded_batches():
    model = _SemanticExplainerModel()
    sql = _chained_sql(14)

    response = ExplainService(llm_client=model).explain(
        SQLExecutionContext(sql=sql, enable_llm=True)
    )

    assert response.success is True
    assert len(response.cte_steps) == 14
    assert response.explain_quality["cte_semantic_explained"] == 14
    # 14 CTE / batch_size 6 => 3 batch calls + 1 final synthesis.
    assert model.calls == 4

    batch_prompts = model.user_prompts[:-1]
    combined = "\n".join(batch_prompts)
    for index in range(14):
        assert f"stage_{index:02d}" in combined

    # No single prompt should receive an unbounded whole-program source dump.
    assert max(map(len, model.user_prompts)) < 30000


def test_llm_failure_degrades_to_deterministic_success():
    response = ExplainService(llm_client=_FailingModel()).explain(
        SQLExecutionContext(sql=SQL, enable_llm=True)
    )

    assert response.success is True
    assert response.explain_quality["llm_enriched"] is False
    assert "llm_error" in response.explain_quality
    assert any(
        "semantic enrichment failed" in item.lower()
        for item in response.uncertainties
    )
