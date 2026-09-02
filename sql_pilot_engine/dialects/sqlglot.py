from __future__ import annotations


SQLGLOT_DIALECT_MAPPING = {
    "maxcompute": "hive",
    "odps": "hive",
    "dataworks": "hive",
    "hive": "hive",
    "spark": "spark",
    "duckdb": "duckdb",
    "mysql": "mysql",
    "postgres": "postgres",
}


def resolve_sqlglot_dialect(
    dialect: str,
) -> str:
    """
    将 Agent3.0 产品层 SQL dialect
    映射为 SQLGlot 实际支持的 dialect。

    例如：

        maxcompute
            ↓
        hive

    注意：
    GeneratedSQL.dialect 仍然保留产品层
    原始 dialect，不把 hive 暴露为业务方言。
    """

    normalized = (
        dialect
        .strip()
        .lower()
    )

    return (
        SQLGLOT_DIALECT_MAPPING
        .get(
            normalized,
            normalized,
        )
    )