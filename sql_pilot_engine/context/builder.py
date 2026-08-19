from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.models import (
    RetrievedDocument,
)
from sql_pilot_engine.context.mandatory_rules import (
    MandatoryRuleMatcher,
)

@dataclass(frozen=True)
class QueryContext:
    question: str

    business_knowledge: tuple[
        RetrievedDocument,
        ...
    ]

    verified_sql: tuple[
        RetrievedDocument,
        ...
    ]

    session_context: tuple[str, ...] = ()

class QueryContextBuilder:

    def __init__(
        self,
        *,
        mandatory_rule_matcher: (MandatoryRuleMatcher | None) = None,
    ) -> None:
        
        self._mandatory_rule_matcher = (mandatory_rule_matcher)

    def build(
        self,
        *,
        question: str,
        business_knowledge: list[
            RetrievedDocument
        ],
        verified_sql: list[
            RetrievedDocument
        ],
        session_context: tuple[str, ...] = (),
    ) -> QueryContext:

        mandatory_rules = (
            self._match_mandatory_rules(
                question
            )
        )
        
        merged_business_knowledge = (
            self._merge_business_knowledge(
                mandatory = mandatory_rules,
                retrieved=tuple(
                    business_knowledge
                ),
            )
        )

        return QueryContext(
            question=question,
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
    ) -> tuple[RetrievedDocument, ...]:
        
        if (self._mandatory_rule_matcher is None):
            return ()
        
        return (
            self._mandatory_rule_matcher.match(question)
        )
        
    @staticmethod
    def _merge_business_knowledge(
        *,
        mandatory: tuple[
            RetrievedDocument, ...
        ],
        retrieved: tuple[
            RetrievedDocument, ...
        ],
    ) -> tuple[RetrievedDocument, ...]:
        """
        Mandatory Rule优先。

        如果同一document_id同时被：
        - Mandatory Rule命中；
        - RAG召回；

        只保留Mandatory版本，避免Prompt重复。
        """
        
        merged: list[
            RetrievedDocument
        ] = []
        
        seen_ids: set[str] = set()
        
        for item in (
            *mandatory,
            *retrieved,
        ):
            document_id = (
                item.document.document_id
            )
            
            if (document_id in seen_ids):
                continue
            
            seen_ids.add(document_id)
            merged.append(item)
        
        return tuple(merged)