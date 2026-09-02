from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp, parse

from sqlglot.errors import ParseError

from sql_pilot_engine.dialects.sqlglot import (
    resolve_sqlglot_dialect,
)

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

        read_dialect = (
            resolve_sqlglot_dialect(
                dialect=dialect
            )
        )

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

