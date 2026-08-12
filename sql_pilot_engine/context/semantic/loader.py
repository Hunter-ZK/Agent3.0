from __future__ import annotations

import json
from pathlib import Path

from sql_pilot_engine.context.semantic.models import (
    SemanticColumn,
    SemanticMetric,
    SemanticModel,
    SemanticTable,
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
                    for column in table["coulmns"]
                )
            )
            for table in raw.get("tables",[])
        )
        
        metrics = tuple(
            SemanticMetric(
                name=metric["name"],
                description=metric["description"],
                expression=metric["expression"],
                table=metric["table"],
                synonyms=tuple(metric.get("synonyms",[])),
            )
            for metric in raw.get("metrics",[])
        )

        return SemanticModel(tables=tables, metrics=metrics,)