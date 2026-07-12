# sql_review_agent/utils/sql_text.py

import re


NON_ASCII_WHITESPACE = {
    "\u3000": " ",
    "\u00a0": " ",
    "\u2002": " ",
    "\u2003": " ",
    "\u2009": " ",
}


def remove_sql_comments(sql: str) -> str:
    """删除 SQL 中的单行和块注释。"""

    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def normalize_sql(sql: str) -> str:
    """用于规则判断的标准化 SQL 文本，不用于覆盖原 SQL。"""

    sql = remove_sql_comments(sql)
    sql = replace_non_ascii_whitespace(sql)
    sql = re.sub(r"\s+", " ", sql)
    return sql.strip().lower()


def contains_non_ascii_whitespace(sql: str) -> bool:
    """判断是否包含全角空格或不可见空白。"""

    return any(char in sql for char in NON_ASCII_WHITESPACE)


def replace_non_ascii_whitespace(sql: str) -> str:
    """替换全角空格和不可见空白为普通空格。"""

    for source, target in NON_ASCII_WHITESPACE.items():
        sql = sql.replace(source, target)
    return sql
