from __future__ import annotations

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.llm.optimizer import LLMOptimizer
from sql_pilot_engine.services.optimize_service import OptimizeService


SUGGESTION = {
    "category": "filter_pushdown",
    "priority": "medium",
    "description": "局部过滤条件前移",
    "reason": "减少中间数据",
    "expected_benefit": "可能减少扫描后的中间行数",
    "risk": "需验证语义等价",
    "requires_execution_validation": True,
}


class _Model:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system_prompt = ""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = user_prompt
        _ = json_schema
        self.system_prompt = system_prompt
        return self.payload


def test_oversized_optimize_uses_scoped_patch():
    sql = "SELECT id FROM project_src.fact WHERE id > 0"
    model = _Model(
        {
            "summary": "局部优化",
            "suggestions": [SUGGESTION],
            "patches": [
                {
                    "old_sql": "id > 0",
                    "new_sql": "id >= 1",
                    "reason": "等价整数边界表达",
                }
            ],
            "rewrite_reason": "局部表达式规范化",
            "assumptions": ["id 为整数"],
            "confidence": 0.8,
        }
    )

    result = LLMOptimizer(
        client=model,
        max_full_rewrite_chars=10,
    ).optimize(
        sql=sql,
        dialect="maxcompute",
        optimization_goals=[],
        analysis_context_text="analysis",
        metadata_context_text="metadata",
        explain_context_text="explain",
        program_evidence_context_text="evidence",
    )

    assert result.candidate_sql is not None
    assert result.candidate_sql.endswith("id >= 1")
    assert "scoped patch planner" in model.system_prompt


def test_optimize_service_rejects_candidate_that_changes_write_target():
    original = """
    INSERT OVERWRITE TABLE project_dwd.result_a
    SELECT id FROM project_src.source_a
    """
    candidate = """
    INSERT OVERWRITE TABLE project_dwd.result_b
    SELECT id FROM project_src.source_a
    """

    model = _Model(
        {
            "summary": "rewrite",
            "suggestions": [SUGGESTION],
            "candidate_sql": candidate,
            "rewrite_reason": "unsafe target change",
            "assumptions": [],
            "confidence": 0.9,
        }
    )

    result = OptimizeService(
        llm_client=model,
    ).optimize(
        SQLExecutionContext(sql=original),
        optimization_goals=[],
    )

    assert result.candidate_sql is None
    assert result.confidence <= 0.5
    assert any(
        "write-target identity" in item
        for item in result.assumptions
    )
