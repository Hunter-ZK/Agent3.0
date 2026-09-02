"""
必须进入当前 QueryContext 的确定性业务规则。

【架构位置】
User Question
    -> MandatoryRuleMatcher（确定性关键词匹配）
    -> RetrievedDocument(score=1.0，仅兼容 DTO)
    -> QueryContextBuilder

【为什么它和 RAG 分开】
向量检索回答的是“哪些文档在语义上相似”；Mandatory Rule 回答的是“只要命中明确业务词，
这条经过确认的规则就必须进入上下文”。如果把后者也交给 Embedding，相似度波动可能导致
关键口径偶尔缺失，因此两条路径必须分开。

【边界】
- 这里不是通用规则引擎，也不执行 SQL Validation；
- 不用 LLM、不用 Embedding，不根据概率判断；
- Rule 文本只是 Business Knowledge，不直接成为 QueryPlan 或 Trusted SQL。
"""

from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.models import (
    ContextDocument,
    ContextDocumentKind,
    RetrievedDocument,
)


@dataclass(
    frozen=True,
    slots=True,
)
class MandatoryBusinessRule:
    """
    一个“明确触发词 -> 必须注入的业务知识文本”定义。

    rule_id 是稳定资产身份；triggers 是确定性包含匹配词；text 是进入 QueryContext 的业务规则正文。
    """

    rule_id: str
    triggers: tuple[str, ...]
    text: str

    def matches(
        self,
        question: str,
    ) -> bool:
        """
        判断问题是否包含任一明确 trigger。

        只 strip 首尾空白，不做同义词扩展、分词或 LLM 推理，保证行为可解释、可重复。
        """

        normalized = question.strip()
        return any(
            trigger in normalized
            for trigger in self.triggers
        )


class MandatoryRuleMatcher:
    """
    顺序执行一组 MandatoryBusinessRule，并把命中项投影成 Context Document。

    V0.1 刻意保持简单：不使用 LLM、Embedding 或复杂优先级系统。多个规则同时命中时全部返回，
    后续 QueryContextBuilder 再与普通 Retrieval 结果按 document_id 去重。
    """

    def __init__(
        self,
        rules: tuple[MandatoryBusinessRule, ...] = (),
    ) -> None:
        # tuple 由 Composition Root / Domain 配置提供；Matcher 本身不动态治理规则资产。
        self._rules = rules

    def match(
        self,
        question: str,
    ) -> tuple[RetrievedDocument, ...]:
        """返回所有确定命中的业务规则，保持规则定义顺序。"""

        matched: list[RetrievedDocument] = []

        for rule in self._rules:
            if not rule.matches(question):
                continue

            # 统一投影为 ContextDocument，让 Builder 无需区分“来自 Mandatory Rule 还是 VectorStore”。
            document = ContextDocument(
                document_id=rule.rule_id,
                kind=ContextDocumentKind.BUSINESS_KNOWLEDGE,
                text=rule.text,
                metadata={"source": "mandatory_rule"},
            )

            matched.append(
                RetrievedDocument(
                    document=document,
                    # score=1.0 仅为了复用 RetrievedDocument Contract；本路径并没有做相似度计算。
                    score=1.0,
                )
            )

        return tuple(matched)
