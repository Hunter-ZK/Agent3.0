from __future__ import annotations

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.llm.optimization_advisor import LLMOptimizationAdvisor
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


def _required(json_schema: dict) -> set[str]:
    schema = json_schema.get("schema", json_schema)
    return set(schema.get("required", []))


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


class _AdvisorThenOptimizeModel:
    def __init__(
        self,
        *,
        opportunities: list[dict],
        optimize_payload: dict | None = None,
    ) -> None:
        self.opportunities = opportunities
        self.optimize_payload = optimize_payload
        self.calls: list[str] = []

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = system_prompt
        _ = user_prompt
        required = _required(json_schema)
        self.calls.append(",".join(sorted(required)))
        if "opportunities" in required:
            return {
                "summary": "advisor summary",
                "opportunities": self.opportunities,
            }
        if "suggestions" in required:
            assert self.optimize_payload is not None
            return self.optimize_payload
        raise AssertionError(f"Unexpected schema: {required}")


def _opportunity(
    *,
    rewrite_safe: bool = True,
    requires_statistics: bool = False,
    confidence: float = 0.95,
) -> dict:
    return {
        "id": "op_1",
        "category": "filter_pushdown",
        "location": "base",
        "evidence": "过滤条件位于上层查询",
        "description": "将可等价下推的过滤条件移动到源表读取层",
        "semantic_argument": "过滤条件只引用单一源表字段且不跨聚合边界",
        "expected_benefit": "可能减少后续算子的中间数据量",
        "priority": "medium",
        "risk": "需要执行验证",
        "confidence": confidence,
        "requires_statistics": requires_statistics,
        "requires_execution_validation": True,
        "rewrite_safe": rewrite_safe,
    }


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
    assert "scoped patch" in model.system_prompt


def test_advisor_forces_statistics_dependent_opportunity_to_suggestions_only():
    model = _Model(
        {
            "summary": "MAPJOIN 是否合适取决于表规模",
            "opportunities": [
                _opportunity(
                    rewrite_safe=True,
                    requires_statistics=True,
                    confidence=0.99,
                )
            ],
        }
    )

    summary, opportunities = LLMOptimizationAdvisor(model).analyze(
        dialect="maxcompute",
        optimization_goals=[],
        analysis_context_text="analysis",
        metadata_context_text="metadata",
        explain_context_text="explain",
        program_evidence_context_text="evidence",
    )

    assert summary
    assert opportunities[0]["requires_statistics"] is True
    assert opportunities[0]["rewrite_safe"] is False


def test_optimize_service_does_not_call_rewriter_without_safe_opportunity():
    model = _AdvisorThenOptimizeModel(
        opportunities=[
            _opportunity(
                rewrite_safe=True,
                requires_statistics=True,
                confidence=0.99,
            )
        ]
    )
    result = OptimizeService(llm_client=model).optimize(
        SQLExecutionContext(sql="SELECT id FROM project_src.fact"),
        optimization_goals=[],
    )

    assert result.candidate_sql is None
    assert result.validation["advisor_gate"] == "suggestions_only"
    assert result.validation["execution_validation"] == "required"
    assert len(model.calls) == 1


def test_optimize_service_rejects_candidate_that_changes_write_target():
    original = """
    INSERT OVERWRITE TABLE project_dwd.result_a
    SELECT id FROM project_src.source_a
    """
    candidate = """
    INSERT OVERWRITE TABLE project_dwd.result_b
    SELECT id FROM project_src.source_a
    """

    model = _AdvisorThenOptimizeModel(
        opportunities=[_opportunity()],
        optimize_payload={
            "summary": "rewrite",
            "suggestions": [SUGGESTION],
            "candidate_sql": candidate,
            "rewrite_reason": "unsafe target change",
            "assumptions": [],
            "confidence": 0.9,
        },
    )

    result = OptimizeService(llm_client=model).optimize(
        SQLExecutionContext(sql=original),
        optimization_goals=[],
    )

    assert result.candidate_sql is None
    assert result.confidence <= 0.5
    assert result.validation["candidate_gate"] == "rejected"
    assert any(
        "write-target identity" in item
        for item in result.assumptions
    )
    assert len(model.calls) == 2


def test_optimize_service_keeps_safe_candidate_and_marks_execution_validation():
    original = "SELECT id FROM project_src.source_a WHERE id > 0"
    candidate = "SELECT id FROM project_src.source_a WHERE id >= 1"
    model = _AdvisorThenOptimizeModel(
        opportunities=[_opportunity()],
        optimize_payload={
            "summary": "局部等价改写",
            "suggestions": [SUGGESTION],
            "candidate_sql": candidate,
            "rewrite_reason": "整数边界等价表达",
            "assumptions": ["id 为整数"],
            "confidence": 0.9,
        },
    )

    result = OptimizeService(llm_client=model).optimize(
        SQLExecutionContext(sql=original),
        optimization_goals=[],
    )

    assert result.candidate_sql == candidate
    assert result.validation["advisor_gate"] == "passed"
    assert result.validation["program_structure"] == "passed"
    assert result.validation["execution_validation"] == "required"
    assert result.opportunities[0]["rewrite_safe"] is True
