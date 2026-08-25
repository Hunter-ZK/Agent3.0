from __future__ import annotations

from dataclasses import dataclass, field



@dataclass(frozen=True)
class SemanticColumn:
    name: str
    description: str
    data_type: str = ""
    synonyms: tuple[str, ...] = ()
    

@dataclass(frozen=True)
class SemanticTable:
    name: str
    description: str
    columns: tuple[SemanticColumn, ...]
    
    synonyms: tuple[str, ...] = ()
    grain: str = ""
    
    
@dataclass(frozen=True)
class SemanticMetric:
    name: str
    description: str
    expression: str
    
    table: str
    
    synonyms: tuple[str, ...] = ()
    

@dataclass(frozen=True)
class SemanticModel:
    tables: tuple[SemanticTable, ...]
    metrics: tuple[SemanticMetric, ...] = ()
    
    def get_table(
        self,
        table_name: str,
    ) -> SemanticTable | None:
        
        normalized = table_name.lower()
        
        for table in self.tables:
            if table.name.lower() == normalized:
                return table
        
        return None

    
    def get_metric(
        self,
        metric_name: str,
    ) -> SemanticMetric | None:

        normalized = (
            metric_name
            .strip()
            .lower()
        )

        for metric in self.metrics:

            if (
                metric.name.lower()
                == normalized
            ):
                return metric

        return None