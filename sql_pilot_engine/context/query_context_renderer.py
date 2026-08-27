from __future__ import annotations

from sql_pilot_engine.context.builder import (
    QueryContext,
)


def render_query_context(
    context: QueryContext | None,
) -> str:
    """
    QueryContext 的唯一文本渲染入口。

    职责：

        QueryContext
            ↓
        canonical text representation

    不负责：
    - Retrieval
    - Context Assembly
    - Prompt 业务规则
    - SQL Analysis
    - Metadata Rendering
    """

    if context is None:
        return "未提供 Query Context。"

    sections: list[str] = []

    # ========================================================
    # User Question
    # ========================================================

    sections.append(
        "## User Question\n"
        f"{context.question}"
    )

    # ========================================================
    # Semantic Context
    # ========================================================

    if context.semantic_context:

        sections.append(
            "## Semantic Context\n"
            f"{context.semantic_context}"
        )

    # ========================================================
    # Business Knowledge
    # ========================================================

    if context.business_knowledge:

        sections.append(
            "## Business Knowledge\n"
            + "\n\n".join(
                item.document.text
                for item
                in context.business_knowledge
            )
        )

    # ========================================================
    # Verified SQL
    # ========================================================

    if context.verified_sql:

        sections.append(
            "## Verified SQL Examples\n"
            + "\n\n".join(
                item.document.text
                for item
                in context.verified_sql
            )
        )

    # ========================================================
    # Session Context
    # ========================================================

    if context.session_context:

        sections.append(
            "## Session Context\n"
            + "\n\n".join(
                context.session_context
            )
        )

    return "\n\n".join(
        sections
    )