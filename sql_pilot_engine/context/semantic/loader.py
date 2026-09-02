from __future__ import annotations

import json
from pathlib import Path

from sql_pilot_engine.context.semantic.models import (
    SemanticColumn,
    SemanticMetric,
    SemanticModel,
    SemanticTable,
    SemanticFilter,
    SemanticFilterValue,
)


class SemanticModelLoader:
    
    def load(
        self,
        path: str | Path,
    ) -> SemanticModel:
        
        model_path = Path(path)
        
        with model_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            raw = json.load(file)
            
        tables = tuple(
            SemanticTable(
                name = table["name"],
                description=table["description"],
                columns=tuple(
                    SemanticColumn(
                        name=column["name"],
                        description=column["description"],
                        data_type=column.get("data_type",""),
                        synonyms=tuple(column.get("synonyms",[])),
                    )
                    for column in table["columns"]
                ),
                synonyms=tuple(
                    table.get("synonyms",[],)
                ),
                grain=table.get("grain","",),
            )
            for table in raw.get("tables",[])
        )
        

        metrics = tuple(
            self._load_metric(
                metric
            )
            for metric
            in raw.get(
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

        aggregation = (
            raw.get(
                "aggregation"
            )
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

            aggreagtion = (
                aggregation
                .strip()
                .lower()
            )

            if not aggregation:
                aggregation = None

        source_column = (
            raw.get(
                "source_column"
            )
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

            description=(
                raw["description"]
            ),

            expression=(
                raw["expression"]
            ),

            table=raw["table"],

            synonyms=tuple(
                raw.get(
                    "synonyms",
                    [],
                )
            ),

            aggregation=(
                aggregation
            ),

            source_column=(
                source_column
            ),

            fixed_filters=tuple(
                self._load_filter(
                    item
                )
                for item
                in raw.get(
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

        return SemanticFilter(
            column=raw[
                "column"
            ],

            operator=raw[
                "operator"
            ],

            value=(
                self._load_filter_value(
                    raw.get(
                        "value"
                    )
                )
            ),
        )

    @staticmethod
    def _load_filter_value(
        value,
    ) -> SemanticFilterValue:

        if isinstance(
            value,
            list,
        ):
            return tuple(
                value
            )

        if (
            value is None
            or isinstance(
                value,
                (
                    str,
                    int,
                    float,
                    bool,
                ),
            )
        ):
            return value

        raise ValueError(
            "Unsupported semantic "
            "filter value."
        )