from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from sql_pilot_engine.dialects.sqlglot import (
    resolve_sqlglot_dialect,
)


@dataclass
class SQLParseResult:
    """
    SQLParser 的结构化解析结果。

    Parser 把“能否解析”作为普通结果返回，而不是把 ParseError 泄漏到所有上层调用方。
    这让 SQL analysis / validation 可以统一处理 success=False 的输入。
    """

    success: bool

    # 保留调用方传入的产品层 dialect，而不是 SQLGlot 内部映射后的 hive 等名称。
    dialect: str

    # SQLGlot 解析出的 AST statement；支持检测多语句而不是只保存第一条。
    statements: list[exp.Expression] = field(
        default_factory=list
    )

    error_message: str | None = None

    # 预留给更高层 analysis 标注无法支持的结构；基础 parser 当前不主动填充。
    unsupported_features: list[str] = field(
        default_factory=list
    )

    @property
    def statement_count(self) -> int:
        """返回实际解析出的 statement 数量，供多语句安全规则直接使用。"""

        return len(self.statements)

    @property
    def first_statement(self) -> exp.Expression | None:
        """便捷访问第一条 AST；空结果时返回 None，而不是抛 IndexError。"""

        if not self.statements:
            return None
        return self.statements[0]


class SQLParser:
    """
    Agent3.0 对 SQLGlot parse() 的薄 Adapter。

    【为什么保留薄 Adapter】
    项目不重写 SQLGlot 的 Parser/Scope/Lineage 算法，但需要把第三方库差异隔离在一层：
    - 统一产品 dialect -> SQLGlot dialect；
    - 把 ParseError 转成 SQLParseResult；
    - 为后续 SQLFacts / Validation 提供稳定入口。

    这层应保持“薄”：不要在 Parser 里塞 capability-specific 业务规则。
    """

    def parse(
        self,
        sql: str,
        dialect: str = "maxcompute",
    ) -> SQLParseResult:
        """
        解析 SQL 文本并返回 AST statements。

        空 SQL 与 SQLGlot ParseError 都是可预期的解析失败，因此返回 success=False；
        真正未预期的编程异常不在这里大范围吞掉。
        """

        normalized_sql = sql.strip()

        if not normalized_sql:
            return SQLParseResult(
                success=False,
                dialect=dialect,
                error_message="SQL cannot be empty",
            )

        # 产品层 maxcompute/odps/dataworks 等别名统一在公共 resolver 中映射，
        # 避免 SQLParser 与 MetricSQLCompiler 各自维护一张不同的 dialect 表。
        read_dialect = resolve_sqlglot_dialect(
            dialect=dialect
        )

        try:
            statements = parse(
                normalized_sql,
                read=read_dialect,
            )

            return SQLParseResult(
                success=True,
                dialect=dialect,
                statements=statements,
            )
        except ParseError as error:
            # ParseError 只代表 SQL 文本无法按目标方言形成 AST，不应被升级成系统异常。
            return SQLParseResult(
                success=False,
                dialect=dialect,
                error_message=str(error),
            )