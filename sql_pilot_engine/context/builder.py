"""
Text-to-SQL 的任务级 QueryContext 与 Context Assembly。

【架构位置】
Long-lived Knowledge Sources
    - Semantic Asset
    - Business Knowledge / Mandatory Rules
    - Verified SQL
    - Session Clarification
            |
            v
      QueryContextBuilder
            |
            v
        QueryContext
            |
            +-> QueryPlanner
            +-> SQLGenerator
            +-> Semantic Validator / LLM Review Context

【核心原则：Knowledge Source != Task Context】
VectorStore、SemanticModel、业务知识文档都是长期知识源；QueryContext 只是当前 Turn 从这些来源中
投影出来的 request-scoped 快照。Builder 不拥有知识源，也不负责 Retrieval、Planning 或 Generation。
"""

from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.mandatory_rules import MandatoryRuleMatcher
from sql_pilot_engine.context.retriever import RetrievedDocument


@dataclass(
    frozen=True,
    slots=True,
)
class QueryContext:
    """
    Text-to-SQL 当前 Turn 的完整任务上下文快照。

    frozen + slots 强调它是构建完成后只读的 request-scoped projection；后续 Stage 不应在原对象上
    追加知识，而应在需要时重新构建新的 QueryContext。
    """

    # 用户这一轮的原始问题，Builder 只做首尾空白规范化，不改写语义。
    question: str

    # SemanticModel 针对当前任务渲染出的文本投影；它不是完整 SemanticModel 本体。
    semantic_context: str

    # Retrieval / Mandatory Rule 已选出的业务知识。顺序保留上游召回和强制规则的优先关系。
    business_knowledge: tuple[RetrievedDocument, ...]

    # 已验证 SQL 示例，仅作为上下文样例，不等于本次问题的最终 SQL。
    verified_sql: tuple[RetrievedDocument, ...]

    # 同一 thread 中用户澄清形成的会话级补充信息；它只影响当前后续 Turn 的任务理解。
    session_context: tuple[str, ...] = ()


class QueryContextBuilder:
    """
    把已经取得的 Context Components 组装成唯一 QueryContext。

    【负责】
    - 规范化当前问题；
    - 根据明确关键词补入 Mandatory Business Rules；
    - 合并 Mandatory Rules 与普通 Retrieval 结果并按 document_id 去重；
    - 冻结 list 输入为 tuple，形成稳定任务快照。

    【不负责】
    - 创建 VectorStore / Embedding；
    - 加载或治理 SemanticModel；
    - 执行向量检索；
    - Query Planning / Schema Linking / SQL Generation；
    - Runtime Routing。
    """

    def __init__(
        self,
        mandatory_rule_matcher: MandatoryRuleMatcher | None = None,
    ) -> None:
        # Matcher 可选：没有配置 Mandatory Rules 时仍然允许构建纯 Retrieval QueryContext。
        self._mandatory_rule_matcher = mandatory_rule_matcher

    def build(
        self,
        *,
        question: str,
        semantic_context: str,
        business_knowledge: list[RetrievedDocument],
        verified_sql: list[RetrievedDocument],
        session_context: tuple[str, ...] = (),
    ) -> QueryContext:
        """
        构建一次不可变 QueryContext。

        输入列表由 Retrieval 层提供；Builder 不重新计算 score，也不重新排序普通召回结果。
        Mandatory Rules 放在普通召回结果之前，以表达“明确业务规则优先于相似度召回”的事实。
        """

        # 只做 strip，避免 Builder 变成第二个 Planner 去解释/重写用户问题。
        normalized_question = question.strip()

        # Mandatory Rule 是关键词确定性命中，不依赖 Embedding；未配置 matcher 时返回空 tuple。
        mandatory_rules = self._match_mandatory_rules(
            normalized_question
        )

        # 业务知识可能同时被 Mandatory Rule 与向量检索命中，因此按稳定 document_id 去重。
        merged_business_knowledge = self._merge_business_knowledge(
            mandatory_rules=mandatory_rules,
            retrieved_documents=tuple(business_knowledge),
        )

        return QueryContext(
            question=normalized_question,
            semantic_context=semantic_context,
            business_knowledge=merged_business_knowledge,
            verified_sql=tuple(verified_sql),
            session_context=session_context,
        )

    def _match_mandatory_rules(
        self,
        question: str,
    ) -> tuple[RetrievedDocument, ...]:
        """执行可选的确定性 Mandatory Rule 匹配；没有 matcher 时显式返回空集合。"""

        if self._mandatory_rule_matcher is None:
            return ()

        return self._mandatory_rule_matcher.match(
            question
        )

    @staticmethod
    def _merge_business_knowledge(
        *,
        mandatory_rules: tuple[RetrievedDocument, ...],
        retrieved_documents: tuple[RetrievedDocument, ...],
    ) -> tuple[RetrievedDocument, ...]:
        """
        合并两类业务知识并按 document_id 去重。

        不能按 text 去重，因为同一文本可能来自不同治理文档；document_id 才是知识资产稳定身份。
        第一次出现的文档保留，所以 Mandatory Rules 天然排在普通 Retrieval 之前。
        """

        merged: list[RetrievedDocument] = []
        seen: set[str] = set()

        for document in (
            *mandatory_rules,
            *retrieved_documents,
        ):
            document_id = document.document.document_id

            if document_id in seen:
                continue

            seen.add(document_id)
            merged.append(document)

        # 转 tuple，避免下游在同一 Turn 内修改召回快照。
        return tuple(merged)
