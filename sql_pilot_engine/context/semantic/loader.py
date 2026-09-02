from __future__ import annotations

import json
from pathlib import Path

from sql_pilot_engine.context.semantic.models import (
    SemanticColumn,
    SemanticFilter,
    SemanticFilterValue,
    SemanticMetric,
    SemanticModel,
    SemanticTable,
)


class SemanticModelLoader:
    """
    Semantic Asset 文件 -> SemanticModel Domain DTO 的反序列化边界。

    【架构位置】
        data / json asset
            ↓
        SemanticModelLoader              <- 本类
            ↓
        SemanticModel
            ├── Context Rendering / Planner
            ├── SchemaLinker
            ├── MetricSQLCompiler
            └── SQLTrustEvidence

    Loader 的职责只有三类：
    1. 读取 JSON；
    2. 做必要的类型/格式标准化；
    3. 构造严格的 Semantic Domain DTO。

    Loader 不负责：
    - 判断指标业务口径是否真实正确；
    - 自动推导/改写指标名称；
    - 从 expression 猜 aggregation/source_column；
    - 自动修复 Semantic Asset。

    这些都属于资产治理或更高层能力。当前阶段明确不把 Semantic Asset 内容准确性作为
    Phase 4.1 开发门槛，但“资产文件能否准确映射成代码 Contract”仍必须可靠。
    """

    def load(
        self,
        path: str | Path,
    ) -> SemanticModel:
        """
        从 JSON 文件加载完整 SemanticModel。

        Path 在入口统一转换，便于调用方既传 str 也传 Path；JSON Decode / File I/O 异常不在
        这里大范围吞掉，因为文件损坏属于真实配置/资产错误，应让 Composition Root 明确看到。
        """

        model_path = Path(path)

        with model_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            raw = json.load(file)

        # Table/Column 目前保持既有 Contract：缺少必填 name/description 时直接 KeyError，
        # 不在 Loader 中偷偷补默认业务含义。
        tables = tuple(
            SemanticTable(
                name=table["name"],
                description=table["description"],
                columns=tuple(
                    SemanticColumn(
                        name=column["name"],
                        description=column["description"],
                        data_type=column.get(
                            "data_type",
                            "",
                        ),
                        synonyms=tuple(
                            column.get(
                                "synonyms",
                                [],
                            )
                        ),
                    )
                    for column in table["columns"]
                ),
                synonyms=tuple(
                    table.get(
                        "synonyms",
                        [],
                    )
                ),
                grain=table.get(
                    "grain",
                    "",
                ),
            )
            for table in raw.get(
                "tables",
                [],
            )
        )

        # Metric 单独走 _load_metric，是因为 Phase 4.1 新增了 aggregation/source_column/
        # fixed_filters 等结构化字段，需要做更严格的类型与空白标准化。
        metrics = tuple(
            self._load_metric(metric)
            for metric in raw.get(
                "metrics",
                [],
            )
        )

        return SemanticModel(
            tables=tables,
            metrics=metrics,
        )

    def _load_metric(
        self,
        raw: dict,
    ) -> SemanticMetric:
        """
        把一个 JSON metric 映射为 SemanticMetric。

        这里不会从 ``expression`` 自动推导简单指标结构。原因是：
        ``SUM(a)`` 看起来可以推导，但复杂方言、别名、过滤聚合等场景很快会让“猜结构”变成
        第二套语义解析器。Phase 4.1 要求 aggregation/source_column 由治理资产显式提供；缺失时
        Compiler 正常返回 COMPLEX_EXPRESSION 并 fallback 到 LLM。
        """

        aggregation = raw.get(
            "aggregation"
        )

        if aggregation is not None:
            if not isinstance(
                aggregation,
                str,
            ):
                raise ValueError(
                    "Metric aggregation "
                    "must be a string or null."
                )

            # 在资产加载边界统一标准化，避免同一指标因为 " SUM " / "sum" 形成不同内存状态。
            aggregation = (
                aggregation
                .strip()
                .lower()
            )

            if not aggregation:
                aggregation = None

        source_column = raw.get(
            "source_column"
        )

        if source_column is not None:
            if not isinstance(
                source_column,
                str,
            ):
                raise ValueError(
                    "Metric source_column "
                    "must be a string or null."
                )

            source_column = (
                source_column
                .strip()
            )

            if not source_column:
                source_column = None

        return SemanticMetric(
            name=raw["name"],
            description=raw["description"],
            expression=raw["expression"],
            table=raw["table"],
            synonyms=tuple(
                raw.get(
                    "synonyms",
                    [],
                )
            ),
            aggregation=aggregation,
            source_column=source_column,
            fixed_filters=tuple(
                self._load_filter(item)
                for item in raw.get(
                    "fixed_filters",
                    [],
                )
            ),
            default_dimensions=tuple(
                raw.get(
                    "default_dimensions",
                    [],
                )
            ),
            unit=raw.get(
                "unit",
                "",
            ),
        )

    def _load_filter(
        self,
        raw: dict,
    ) -> SemanticFilter:
        """
        反序列化一个指标固定过滤。

        column/operator 是固定过滤最小必需事实，因此使用必填 key；value 允许 None，实际某个
        operator 是否支持 None 仍由 Compiler 的安全过滤构建器决定。
        """

        return SemanticFilter(
            column=raw["column"],
            operator=raw["operator"],
            value=self._load_filter_value(
                raw.get("value")
            ),
        )

    @staticmethod
    def _load_filter_value(
        value,
    ) -> SemanticFilterValue:
        """
        把 JSON filter value 限制到 SemanticFilterValue Contract。

        JSON list 转 tuple，是为了让 frozen Semantic DTO 内部也保持不可变集合语义；
        dict / nested object 等复杂结构当前不在 V1 fixed filter 能力边界内，直接拒绝而不是猜。
        """

        scalar_types = (
            str,
            int,
            float,
            bool,
        )

        if isinstance(
            value,
            list,
        ):
            # SemanticFilterValue 只允许“标量 tuple”。如果 JSON list 中混入 dict/list，
            # 不能仅因为外层是 list 就放进 Domain DTO，否则类型 Contract 与真实数据会不一致。
            if not all(
                item is None
                or isinstance(
                    item,
                    scalar_types,
                )
                for item in value
            ):
                raise ValueError(
                    "Unsupported semantic "
                    "filter value item."
                )

            return tuple(value)

        if (
            value is None
            or isinstance(
                value,
                scalar_types,
            )
        ):
            return value

        raise ValueError(
            "Unsupported semantic "
            "filter value."
        )