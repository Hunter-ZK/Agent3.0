from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.mandatory_rules import (
    MandatoryRuleMatcher,
)
from sql_pilot_engine.context.retriever import (
    RetrievedDocument,
)


@dataclass(
    frozen=True,
    slots=True,
)
class QueryContext:
    """
    Text-to-SQL 当前 Turn 的完整任务上下文。

    注意：
    QueryContext 是 request-scoped projection，
    不是长期 Knowledge Source。
    """

    question: str

    # SemanticModel 针对当前问题渲染出的任务级投影。
    semantic_context: str

    business_knowledge: tuple[
        RetrievedDocument,
        ...
    ]

    verified_sql: tuple[
        RetrievedDocument,
        ...
    ]

    session_context: tuple[
        str,
        ...
    ] = ()


class QueryContextBuilder:
    """
    Text-to-SQL Context Assembly。

    负责：
        已取得的 Context Components
        → QueryContext

    不负责：
        - 创建 VectorStore
        - 加载 SemanticModel
        - Query Planning
        - SQL Generation
        - Runtime Routing
    """

    def __init__(
        self,
        mandatory_rule_matcher: (
            MandatoryRuleMatcher | None
        ) = None,
    ) -> None:
        self._mandatory_rule_matcher = (
            mandatory_rule_matcher
        )

    def build(
        self,
        *,
        question: str,
        semantic_context: str,

        business_knowledge: list[
            RetrievedDocument
        ],

        verified_sql: list[
            RetrievedDocument
        ],

        session_context: tuple[
            str,
            ...
        ] = (),
    ) -> QueryContext:

        normalized_question = (
            question.strip()
        )

        mandatory_rules = (
            self._match_mandatory_rules(
                normalized_question
            )
        )

        merged_business_knowledge = (
            self._merge_business_knowledge(
                mandatory_rules=(
                    mandatory_rules
                ),
                retrieved_documents=tuple(
                    business_knowledge
                ),
            )
        )

        return QueryContext(
            question=normalized_question,

            semantic_context=(
                semantic_context
            ),

            business_knowledge=(
                merged_business_knowledge
            ),

            verified_sql=tuple(
                verified_sql
            ),

            session_context=(
                session_context
            ),
        )

    def _match_mandatory_rules(
        self,
        question: str,
    ) -> tuple[
        RetrievedDocument,
        ...
    ]:

        if (
            self._mandatory_rule_matcher
            is None
        ):
            return ()

        return (
            self._mandatory_rule_matcher
            .match(question)
        )

    @staticmethod
    def _merge_business_knowledge(
        *,
        mandatory_rules: tuple[
            RetrievedDocument,
            ...
        ],

        retrieved_documents: tuple[
            RetrievedDocument,
            ...
        ],
    ) -> tuple[
        RetrievedDocument,
        ...
    ]:

        merged: list[
            RetrievedDocument
        ] = []

        seen: set[str] = set()

        for document in (
            *mandatory_rules,
            *retrieved_documents,
        ):

            document_id = (
                document.document_id
            )

            if document_id in seen:
                continue

            seen.add(document_id)

            merged.append(document)

        return tuple(merged)