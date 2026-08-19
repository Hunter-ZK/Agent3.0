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
    当问题明确命中某个稳定业务概念时，
    必须进入Context的业务规则。

    与RAG不同：
    这里不依赖Embedding相似度。
    """

    rule_id: str
    triggers: tuple[str, ...]
    text: str

    def matches(
        self,
        question: str,
    ) -> bool:
        normalized = question.strip()

        return any(
            trigger in normalized
            for trigger in self.triggers
        )


class MandatoryRuleMatcher:
    """
    根据明确关键词触发Mandatory Rules。

    V0.1刻意保持简单：
    - 不使用LLM
    - 不使用Embedding
    - 不做复杂规则引擎
    """

    def __init__(
        self,
        rules: tuple[
            MandatoryBusinessRule,
            ...
        ] = (),
    ) -> None:
        self._rules = rules

    def match(
        self,
        question: str,
    ) -> tuple[
        RetrievedDocument,
        ...
    ]:
        matched: list[
            RetrievedDocument
        ] = []

        for rule in self._rules:
            if not rule.matches(
                question
            ):
                continue

            document = ContextDocument(
                document_id=(
                    rule.rule_id
                ),

                kind=(
                    ContextDocumentKind
                    .BUSINESS_KNOWLEDGE
                ),

                text=rule.text,

                metadata={
                    "source": (
                        "mandatory_rule"
                    ),
                },
            )

            matched.append(
                RetrievedDocument(
                    document=document,

                    # score仅用于保持现有DTO契约。
                    # Mandatory Rule不是通过
                    # 相似度排序产生的。
                    score=1.0,
                )
            )

        return tuple(matched)