# sql_review_agent/metadata/models.py

from dataclasses import dataclass


@dataclass
class ColumnMetadata:
    """字段元数据。"""

    name: str
    data_type: str
    comment: str = ""


@dataclass
class TableMetadata:
    """表元数据。"""

    table_name: str
    layer: str
    is_partitioned: bool
    partition_fields: list[str]
    columns: list[ColumnMetadata]
    comment: str = ""

    def column_names(self) -> set[str]:
        return {column.name.lower() for column in self.columns}
