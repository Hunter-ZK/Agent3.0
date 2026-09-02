"""
SemanticModel 的标准文本渲染器。

【架构位置】
SemanticModel(structured source of truth)
    -> SemanticModelRenderer.render()
    -> semantic_context(text projection)
    -> QueryContext
    -> Planner / Generator Prompt

【为什么需要 Renderer】
Planner/LLM 需要文本上下文，但 SemanticModel 的事实源应该保持结构化 DTO。Renderer 负责把同一份
资产生成稳定文本投影，避免每个 Prompt Builder 各自拼一套格式并产生口径漂移。

【边界】
- Renderer 不修改、不补全、不验证 Semantic Asset；
- 文本只是 Prompt Projection，不取代 SemanticModel 本体；
- 不在这里做 Retrieval、Schema Linking 或 SQL Generation。
"""

from __future__ import annotations

from sql_pilot_engine.context.semantic.models import SemanticModel


class SemanticModelRenderer:
    """把结构化 SemanticModel 渲染成供 LLM/Prompt 消费的 canonical text。"""

    def render(
        self,
        model: SemanticModel,
    ) -> str:
        """
        按 Table -> Column -> Metric 的固定顺序生成文本。

        保持稳定顺序很重要：同一 SemanticModel 不应因为 dict/临时排序差异导致 Prompt 无意义变化，
        这也有利于 Evaluation 对比和 Prompt 调试。
        """

        lines: list[str] = []

        # Stage 1：先渲染物理/逻辑表与列，让 Planner 能看到可用实体、粒度和同义词。
        for table in model.tables:
            synonyms = ", ".join(table.synonyms)

            lines.append(
                f"TABLE {table.name}: "
                f"{table.description}"
                f"grain={table.grain}; "
                f"synonyms=[{synonyms}]"
            )

            for column in table.columns:
                synonyms = ", ".join(column.synonyms)

                lines.append(
                    f" COLUMN {column.name} "
                    f"[{column.data_type}]: "
                    f"{column.description}; "
                    f"synonyms=[{synonyms}]"
                )

        # Stage 2：再渲染指标定义。expression 保留完整口径，供复杂指标的 LLM 路径参考。
        for metric in model.metrics:
            synonyms = ", ".join(metric.synonyms)

            lines.append(
                f"METRIC {metric.name}: "
                f"{metric.description}; "
                f"table={metric.table}; "
                f"expression={metric.expression}; "
                f"synonyms=[{synonyms}]"
            )

        return "\n".join(lines)
