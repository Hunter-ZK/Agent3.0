from __future__ import annotations

from sql_pilot_engine.engine import (
    SQLPilotEngine,
)
from sql_pilot_engine.schemas.requests import (
    SQLOptimizeRequest,
)
from sql_pilot_engine.services.optimize_service import (
    OptimizeService,
)
from sql_pilot_engine.services.review_service import (
    ReviewService,
)


class FakeOptimizeLLM:

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:

        assert "Optimization" in (
            system_prompt
        )

        assert "SELECT" in (
            user_prompt
        )

        _ = json_schema

        return {
            "summary": (
                "存在一个可维护性优化机会。"
            ),
            "suggestions": [],
            "candidate_sql": (
                "SELECT id FROM t"
            ),
            "rewrite_reason": (
                "保持语义不变并简化 SQL。"
            ),
            "assumptions": [],
            "confidence": 0.9,
        }


def test_engine_optimize_returns_candidate():

    engine = SQLPilotEngine(
        review_service=ReviewService(),
        optimize_service=(
            OptimizeService(
                llm_client=(
                    FakeOptimizeLLM()
                )
            )
        ),
    )

    response = engine.optimize(
        SQLOptimizeRequest(
            sql="SELECT id FROM t",
            enable_metadata=False,
            optimization_goals=[
                "提高可维护性"
            ],
        )
    )

    assert response.success is True

    assert (
        response.status
        == "candidate_generated"
    )

    assert (
        response.candidate_sql
        == "SELECT id FROM t"
    )

    assert (
        response.confidence
        == 0.9
    )


def test_engine_optimize_without_service_fails_cleanly():

    engine = SQLPilotEngine(
        review_service=ReviewService(),
    )

    response = engine.optimize(
        SQLOptimizeRequest(
            sql="SELECT id FROM t",
        )
    )

    assert response.success is False

    assert (
        response.status
        == "optimize_failed"
    )

    assert (
        response.candidate_sql
        is None
    )