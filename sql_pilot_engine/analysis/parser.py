# sql_review_agent/analysis/parser.py

import re
from dataclasses import dataclass

from sql_pilot_engine.utils.sql_text import normalize_sql

IDENTIFIER_PATTERN = r"[a-zA-Z_][a-zA-Z0-9_]*"
QUALIFIED_NAME_PATTERN = rf"{IDENTIFIER_PATTERN}(?:\.{IDENTIFIER_PATTERN})*"

SQL_KEYWORDS = {
    "where", "on", "join", "left", "right", "inner", "outer", "full",
    "cross", "group", "order", "limit", "having", "union", "select",
    "from", "and", "or", "as", "lateral", "view", "explode", "partition",
}


@dataclass
class ColumnReference:
    table_alias: str | None
    column_name: str
    expression: str


def extract_insert_target_table(sql: str) -> str | None:
    normalized = normalize_sql(sql)
    pattern = rf"\binsert\s+(overwrite|into)\s+(table\s+)?({QUALIFIED_NAME_PATTERN})"
    match = re.search(pattern, normalized)
    if not match:
        return None
    return match.group(3).lower()


def extract_source_tables(sql: str) -> list[str]:
    normalized = normalize_sql(sql)
    pattern = rf"\b(from|join)\s+({QUALIFIED_NAME_PATTERN})"
    tables = [match.group(2).lower() for match in re.finditer(pattern, normalized)]
    return list(dict.fromkeys(tables))


def extract_table_aliases(sql: str) -> dict[str, str]:
    normalized = normalize_sql(sql)
    pattern = (
        rf"\b(from|join)\s+({QUALIFIED_NAME_PATTERN})"
        rf"(?:\s+(?:as\s+)?({IDENTIFIER_PATTERN}))?"
    )
    alias_map: dict[str, str] = {}

    for match in re.finditer(pattern, normalized):
        table_name = match.group(2).lower()
        alias = match.group(3)
        alias_map[table_name] = table_name
        alias_map[table_name.split(".")[-1]] = table_name
        if alias and alias.lower() not in SQL_KEYWORDS:
            alias_map[alias.lower()] = table_name

    return alias_map


def has_partition_clause(sql: str) -> bool:
    return re.search(r"\bpartition\s*\(", normalize_sql(sql)) is not None


def split_sql_statements(sql: str) -> list[str]:
    return [item.strip() for item in sql.split(";") if item.strip()]


def extract_select_clause(sql: str) -> str | None:
    normalized = normalize_sql(sql)
    match = re.search(r"\bselect\b(.*?)\bfrom\b", normalized, flags=re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def split_select_items(select_clause: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0

    for char in select_clause:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)

        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)

    last_item = "".join(current).strip()
    if last_item:
        items.append(last_item)

    return items


def strip_output_alias(expression: str) -> str:
    expression = expression.strip()
    expression = re.sub(rf"\s+as\s+{IDENTIFIER_PATTERN}$", "", expression, flags=re.IGNORECASE)
    expression = re.sub(rf"(\))\s+{IDENTIFIER_PATTERN}$", r"\1", expression)
    return expression.strip()


def extract_select_column_references(sql: str) -> list[ColumnReference]:
    select_clause = extract_select_clause(sql)
    if not select_clause:
        return []

    refs: list[ColumnReference] = []

    for item in split_select_items(select_clause):
        expression = strip_output_alias(item)
        qualified_matches = list(re.finditer(rf"\b({IDENTIFIER_PATTERN})\.({IDENTIFIER_PATTERN})\b", expression))

        if qualified_matches:
            for match in qualified_matches:
                refs.append(
                    ColumnReference(
                        table_alias=match.group(1).lower(),
                        column_name=match.group(2).lower(),
                        expression=expression,
                    )
                )
            continue

        if re.fullmatch(IDENTIFIER_PATTERN, expression):
            refs.append(ColumnReference(table_alias=None, column_name=expression.lower(), expression=expression))

    return refs


def extract_output_columns(sql_fragment: str) -> list[str]:
    select_clause = extract_select_clause(sql_fragment)
    if not select_clause:
        return []

    output_columns: list[str] = []

    for item in split_select_items(select_clause):
        item = item.strip()
        as_match = re.search(rf"\s+as\s+({IDENTIFIER_PATTERN})$", item, flags=re.IGNORECASE)
        if as_match:
            output_columns.append(as_match.group(1).lower())
            continue

        tail_alias_match = re.search(rf"\)\s+({IDENTIFIER_PATTERN})$", item)
        if tail_alias_match:
            output_columns.append(tail_alias_match.group(1).lower())
            continue

        expr = strip_output_alias(item)
        simple_col_match = re.fullmatch(rf"({IDENTIFIER_PATTERN})(\.({IDENTIFIER_PATTERN}))?", expr)
        if simple_col_match:
            output_columns.append((simple_col_match.group(3) or simple_col_match.group(1)).lower())

    return list(dict.fromkeys(output_columns))


def extract_cte_names(sql: str) -> set[str]:
    normalized = normalize_sql(sql)
    if not normalized.startswith("with "):
        return set()
    return {match.group(1).lower() for match in re.finditer(rf"\b({IDENTIFIER_PATTERN})\s+as\s*\(", normalized)}
