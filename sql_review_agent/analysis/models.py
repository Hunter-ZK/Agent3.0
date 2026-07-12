# sql_review_agent/analysis/models.py

from dataclasses import dataclass, field


@dataclass
class SQLRelation:
    relation_name: str
    alias: str | None = None
    relation_type: str = "unknown"


@dataclass
class SQLCTE:
    name: str
    body: str
    output_columns: list[str] = field(default_factory=list)
    referenced_relations: list[SQLRelation] = field(default_factory=list)


@dataclass
class SQLStatement:
    statement_type: str
    raw_sql: str
    target_table: str | None = None
    source_relations: list[SQLRelation] = field(default_factory=list)
    features: dict[str, bool] = field(default_factory=dict)


@dataclass
class SQLAnalysisResult:
    dialect: str
    original_sql: str
    ctes: dict[str, SQLCTE] = field(default_factory=dict)
    statements: list[SQLStatement] = field(default_factory=list)
    file_features: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
