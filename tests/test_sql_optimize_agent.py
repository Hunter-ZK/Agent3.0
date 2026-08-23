from sql_pilot_engine.agents.sql_optimize_agent import (
    SQLOptimizeAgent,
)
from sql_pilot_engine.optimization.context import (
    SQLOptimizationContext,
)


class FakeLLMClient:

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:

        assert "MaxCompute" in (
            system_prompt
        )

        assert "SELECT" in (
            user_prompt
        )

        assert json_schema[
            "type"
        ] == "object"

        return {
            "summary": (
                "发现可以提前过滤数据。"
            ),
            "suggestions": [
                {
                    "category": (
                        "filter_pushdown"
                    ),
                    "priority": "high",
                    "description": (
                        "建议提前过滤数据。"
                    ),
                    "reason": (
                        "减少后续 JOIN 输入量。"
                    ),
                    "expected_benefit": (
                        "可能降低扫描和 Shuffle。"
                    ),
                    "risk": (
                        "需确认过滤条件语义。"
                    ),
                    "requires_execution_validation": True,
                }
            ],
            "candidate_sql": (
                "SELECT id "
                "FROM t "
                "WHERE dt = '202607'"
            ),
            "rewrite_reason": (
                "将已知过滤条件提前。"
            ),
            "assumptions": [
                "dt 为业务有效时间条件"
            ],
            "confidence": 0.83,
        }


def test_llm_optimizer_returns_proposal():

    agent = SQLOptimizeAgent(
        llm_client=FakeLLMClient()
    )

    result = agent.optimize(
        SQLOptimizationContext(
            sql="SELECT id FROM t",
            dialect="maxcompute",
            optimization_goals=(
                "减少扫描量",
            ),
        )
    )

    assert (
        result.candidate_sql
        is not None
    )

    assert (
        len(result.suggestions)
        == 1
    )

    assert (
        result.suggestions[
            0
        ].category
        == "filter_pushdown"
    )

    assert result.confidence == 0.83