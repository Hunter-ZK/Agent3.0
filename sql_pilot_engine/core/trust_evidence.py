"""
Text-to-SQL 向 Trusted SQL Gate 传递的任务级结构化证据。

架构位置：
QueryPlanner -> QueryPlan
SchemaLinker -> LinkedSchema
Semantic Asset -> SemanticModel
三者共同组成 SQLTrustEvidence，再进入 TrustedSQLWorkflow / Rules。

为什么单独建 SQLTrustEvidence：
Trust Gate 需要同时知道“用户想查什么”“逻辑意图落到了哪些物理资产”“批准的语义资产是什么”。
如果这些对象被散落成多个可选参数，Rule 很容易只读取其中一部分并做过度推断。
因此 SQLTrustEvidence 把本次任务已经确认的三类结构化证据绑定成一个只读 Contract。

边界：
- 它不是 QueryContext：不保存 RAG 文本、会话历史等业务上下文；
- 它不是 SQLFacts：SQLFacts 必须从待审 SQL 本身通过 SQLAnalysisAdapter 生成；
- 它不复制 Metadata：LinkedSchema 中已经保存本次解析到的物理落点；
- 它只提供证据，不直接决定 IssueAction。
"""

from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.semantic.models import SemanticModel
from sql_pilot_engine.generation.models import QueryPlan
from sql_pilot_engine.linking.models import LinkedSchema


@dataclass(
    frozen=True,
    slots=True,
)
class SQLTrustEvidence:
    """Trusted SQL Gate 的任务级只读结构化证据快照。"""

    query_plan: QueryPlan
    linked_schema: LinkedSchema
    semantic_model: SemanticModel
