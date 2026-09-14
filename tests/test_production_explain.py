from __future__ import annotations

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.services.explain_service import ExplainService


SQL = """
WITH base AS (
    SELECT id, amount
    FROM project_src.loan_detail
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


class _FakeExplainerModel:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = json_schema
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return {
            "sql_summary": "LLM semantic summary",
            "business_purpose": "汇总贷款金额",
            # Deliberately hallucinated structural facts. They must not replace deterministic evidence.
            "main_tables": [{"table": "hallucinated.table"}],
            "output_columns": [{"target": "hallucinated.column"}],
            "cte_steps": [{"name": "hallucinated_cte"}],
            "cte_dependencies": [],
            "suspicious_points": [
                {
                    "type": "semantic_review",
                    "message": "请确认业务口径",
                }
            ],
            "uncertainties": ["业务定义需要确认"],
            "route_signals": {},
        }


def test_explain_works_without_llm_and_uses_program_facts():
    response = ExplainService().explain(
        SQLExecutionContext(sql=SQL)
    )

    assert response.success is True
    assert "1 statement(s)" in response.sql_summary
    assert "2 CTE(s)" in response.sql_summary

    assert {item["table"] for item in response.main_tables} == {
        "project_src.loan_detail",
        "project_dwd.loan_summary",
    }
    assert [item["name"] for item in response.cte_steps] == [
        "base",
        "agg",
    ]
    assert response.business_purpose is None
    assert response.route_signals["need_review"] is True


def test_llm_enriches_semantics_but_cannot_override_deterministic_structure():
    model = _FakeExplainerModel()
    service = ExplainService(llm_client=model)

    response = service.explain(
        SQLExecutionContext(
            sql=SQL,
            enable_llm=True,
        )
    )

    assert response.success is True
    assert response.sql_summary == "LLM semantic summary"
    assert response.business_purpose == "汇总贷款金额"

    assert {item["table"] for item in response.main_tables} == {
        "project_src.loan_detail",
        "project_dwd.loan_summary",
    }
    assert all(
        item.get("table") != "hallucinated.table"
        for item in response.main_tables
    )
    assert [item["name"] for item in response.cte_steps] == [
        "base",
        "agg",
    ]
    assert any(
        item.get("type") == "semantic_review"
        for item in response.suspicious_points
    )
    assert "Deterministic Program / Evidence Context" in model.user_prompt


def test_long_sql_is_not_sent_to_llm_as_unbounded_one_shot_prompt():
    model = _FakeExplainerModel()
    service = ExplainService(llm_client=model)

    repeated = "\n".join(
        f"-- padding {index} " + ("x" * 80)
        for index in range(500)
    )
    long_sql = SQL + "\n" + repeated

    response = service.explain(
        SQLExecutionContext(
            sql=long_sql,
            enable_llm=True,
        )
    )

    assert response.success is True
    assert "SQL EXCERPT TRUNCATED" in model.user_prompt
    assert len(model.user_prompt) < len(long_sql) + 20000
