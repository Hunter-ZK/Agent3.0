from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.semantic.models import (
    SemanticModel,
)

from sql_pilot_engine.generation.models import (
    QueryPlan,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
)


@dataclass(
    frozen=True,
    slots=True,
)
class SQLTrustEvidence:
    """
    Trusted SQL Gate 的任务级结构化证据。

    它不是新的 TaskContext，也不是第二份 Metadata。

    query_plan:
        Planner 对本次用户意图的结构化解释。

    linked_schema:
        QueryPlan 已确认的物理落点。

    semantic_model:
        当前已批准的 Semantic Asset。

    SQLFacts 不放在这里：
        SQLFacts 由 SQLAnalysisAdapter
        在 Review 阶段从待审 SQL 生成。
    """

    query_plan: QueryPlan

    linked_schema: LinkedSchema

    semantic_model: SemanticModel