from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp, parse

from sqlglot.errors import ParseError

DIALECT_MAPPING = {
    "maxcompute": "hive",
    "odps": "hive",
    "dataworks": "hive",
    "hive": "hive",
    "spark": "spark",
    "duckdb": "duckdb",
    "mysql": "mysql",
    "postgres": "postgres",
}


@dataclass
class SQLParseResult:
    success: bool
    dialect: str

    statements: list[exp.Expression] = field(default_factory=list)

    error_message: str | None = None

    unsupported_features: list[str] = field(default_factory=list)

    @property
    def statement_count(self) -> int:
        return len(self.statements)
    
    @property
    def first_statement(self,) -> exp.Expression | None:
        if not self.statements:
            return None
        
        return self.statements[0]
    

class SQLParser:

    def parse(
        self,
        sql: str,
        dialect: str = "maxcompute",
    ) -> SQLParseResult:
        
        normalize_sql = sql.strip()

        if not normalize_sql:
            return SQLParseResult(
                success=False,
                dialect=dialect,
                error_message="SQL cannot be empty",
            )

        read_dialect = self._resolve_dialect(dialect)

        try:
            statements = parse(
                normalize_sql,
                read = read_dialect,
            )

            return SQLParseResult(
                success=True,
                dialect=dialect,
                statements=statements,
            )
        except ParseError as error:
            return SQLParseResult(
                success=False,
                dialect=dialect,
                error_message=str(error),
            )

    @staticmethod
    def _resolve_dialect(
        dialect: str,
    ) -> str:
        normalized = dialect.strip().lower()
        return DIALECT_MAPPING.get(normalized,normalized,)

