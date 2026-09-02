from __future__ import annotations

from dataclasses import dataclass



SemanticScalar = (
    str
    | int
    | float
    | bool
    | None
)

SemanticFilterValue = (
    SemanticScalar
    | tuple[
        SemanticScalar,
        ...
    ]
)



@dataclass(frozen=True)
class SemanticFilter:
    """
    Semantic Asset 中声明的固定过滤条件。

    注意：
    这是已经治理确认的业务事实，
    不是 Runtime 从自然语言中猜出的条件。
    """
    
    column: str
    
    operator: str
    
    value: SemanticFilterValue
    
    def __post_init__(
        self,
    ) -> None:

        if not self.column.strip():
            raise ValueError(
                "SemanticFilter.column "
                "cannot be empty."
            )

        if not self.operator.strip():
            raise ValueError(
                "SemanticFilter.operator "
                "cannot be empty."
            )



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
    """
    Governed Metric Asset。

    expression:
        完整业务表达式。
        用于 Prompt、Generator、
        LLM Reviewer 和复杂指标。

    aggregation + source_column:
        可形式化的简单指标语义。
        后续 Deterministic Gate
        优先读取这里，而不是重新解析
        expression 猜测指标定义。

    fixed_filters:
        指标自身固有的业务过滤条件。

    当前 table 字段继续承担 source_table
    的职责，不做无意义重命名。
    """
    name: str
    description: str
    expression: str
    
    table: str
    
    synonyms: tuple[str, ...] = ()
    
    aggregation: str | None = None
    
    source_column: str | None = None
    
    fixed_filters: tuple[SemanticFilter, ...] = ()
    
    default_dimensions: tuple[str, ...] = ()
    
    unit: str = ""
    
    def __post_init__(
        self,
    ) -> None:

        if not self.name.strip():
            raise ValueError(
                "SemanticMetric.name "
                "cannot be empty."
            )

        if not self.table.strip():
            raise ValueError(
                "SemanticMetric.table "
                "cannot be empty."
            )

        if not self.expression.strip():
            raise ValueError(
                "SemanticMetric.expression "
                "cannot be empty."
            )

        if (
            self.aggregation is not None
            and not self.aggregation.strip()
        ):
            raise ValueError(
                "SemanticMetric.aggregation "
                "cannot be blank."
            )

        if (
            self.source_column is not None
            and not self.source_column.strip()
        ):
            raise ValueError(
                "SemanticMetric.source_column "
                "cannot be blank."
            )
            
            

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