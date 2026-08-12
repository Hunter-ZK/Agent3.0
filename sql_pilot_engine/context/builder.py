from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.context.models import (
    RetrievedDocument,
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


class QueryContextBuilder:

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
    ) -> QueryContext:

        return QueryContext(
            question=question,
            business_knowledge=tuple(
                business_knowledge
            ),
            verified_sql=tuple(
                verified_sql
            ),
        )