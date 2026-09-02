from __future__ import annotations


# Agent3.0 对外使用“产品/平台方言”名称，但 SQLGlot 并不一定为这些名字提供独立 Dialect。
# 例如 MaxCompute / ODPS / DataWorks 当前都复用 SQLGlot 的 Hive 语法能力。
#
# 这张映射表集中在一个公共模块中的原因：
# 1. SQLParser、MetricSQLCompiler 等多个组件都会调用 SQLGlot；
# 2. 如果每个组件各自维护映射，后续新增或修正方言时很容易发生行为漂移；
# 3. GeneratedSQL.dialect 仍应保留产品层方言，映射只属于 SQLGlot adapter 内部实现细节。
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
    把 Agent3.0 产品层 SQL dialect 转换成 SQLGlot 实际识别的 dialect 名称。

    【调用方】
    - SQLParser：决定 ``sqlglot.parse(..., read=...)`` 使用什么解析器；
    - MetricSQLCompiler：决定过滤 AST 解析和最终 AST 渲染使用什么方言。

    【为什么未知方言原样返回】
    SQLGlot 自身支持的方言集合会演进，Agent3.0 没必要在这里复制一份完整枚举。
    已知“产品别名”做显式转换；其它名称交给 SQLGlot 自己处理。若 SQLGlot 不支持，
    应由真正的 parse/render 调用给出错误，而不是这个 resolver 猜测。

    示例：
        maxcompute -> hive
        odps       -> hive
        postgres   -> postgres

    注意：这个函数只返回 SQLGlot adapter 使用的名称，不会修改 GeneratedSQL.dialect。
    """

    normalized = dialect.strip().lower()
    return SQLGLOT_DIALECT_MAPPING.get(
        normalized,
        normalized,
    )