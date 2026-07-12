# sql_review_agent/analysis/analyzer.py

import re

from sql_review_agent.analysis.models import SQLAnalysisResult, SQLCTE, SQLRelation, SQLStatement
from sql_review_agent.analysis.parser import (
    extract_insert_target_table,
    extract_output_columns,
    extract_source_tables,
    split_sql_statements,
)
from sql_review_agent.utils.sql_text import normalize_sql


def analyze_sql(sql: str, dialect: str = "maxcompute") -> SQLAnalysisResult:
    result = SQLAnalysisResult(dialect=dialect, original_sql=sql)
    result.ctes = extract_ctes(sql)
    result.statements = analyze_statements(sql)
    result.file_features = build_file_features(sql, result)
    result.warnings = detect_text_warnings(sql)
    mark_cte_relations(result)
    return result


def extract_ctes(sql: str) -> dict[str, SQLCTE]:
    lower_sql = sql.lower()
    with_match = re.search(r"\bwith\b", lower_sql)
    if not with_match:
        return {}

    index = with_match.end()
    ctes: dict[str, SQLCTE] = {}

    while index < len(sql):
        while index < len(sql) and sql[index] in {" ", "\n", "\t", "\r", ","}:
            index += 1

        name_match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", sql[index:], flags=re.IGNORECASE)
        if not name_match:
            break

        cte_name = name_match.group(1).lower()
        body_start = index + name_match.end()
        body_end = find_matching_parenthesis(sql, body_start - 1)
        if body_end is None:
            break

        body = sql[body_start:body_end]
        ctes[cte_name] = SQLCTE(
            name=cte_name,
            body=body,
            output_columns=extract_output_columns(body),
            referenced_relations=[SQLRelation(relation_name=table) for table in extract_source_tables(body)],
        )
        index = body_end + 1

    return ctes


def find_matching_parenthesis(sql: str, open_pos: int) -> int | None:
    depth = 0
    for index in range(open_pos, len(sql)):
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def analyze_statements(sql: str) -> list[SQLStatement]:
    statements: list[SQLStatement] = []
    for raw_statement in split_sql_statements(sql):
        normalized = normalize_sql(raw_statement)
        if normalized.startswith("set "):
            statement_type = "set"
        elif re.search(r"\binsert\s+(overwrite|into)\b", normalized):
            statement_type = "insert"
        elif normalized.startswith("select") or normalized.startswith("with"):
            statement_type = "select"
        else:
            statement_type = "unknown"

        statements.append(
            SQLStatement(
                statement_type=statement_type,
                raw_sql=raw_statement,
                target_table=extract_insert_target_table(raw_statement),
                source_relations=[SQLRelation(relation_name=table) for table in extract_source_tables(raw_statement)],
                features=build_statement_features(raw_statement),
            )
        )
    return statements


def build_statement_features(sql: str) -> dict[str, bool]:
    normalized = normalize_sql(sql)
    wrapped = f" {normalized} "
    return {
        "has_join": " join " in wrapped,
        "has_group_by": " group by " in wrapped,
        "has_union_all": " union all " in wrapped,
        "has_lateral_view": " lateral view " in wrapped,
        "has_map": re.search(r"\bmap\s*\(", normalized) is not None,
        "has_explode": re.search(r"\bexplode\s*\(", normalized) is not None,
        "has_grouping_sets": " grouping sets " in wrapped,
        "has_distribute_by": " distribute by " in wrapped,
    }


def build_file_features(sql: str, result: SQLAnalysisResult) -> dict[str, bool]:
    normalized = normalize_sql(sql)
    wrapped = f" {normalized} "
    return {
        "has_cte": len(result.ctes) > 0,
        "has_multiple_statements": len(result.statements) > 1,
        "has_insert": any(item.statement_type == "insert" for item in result.statements),
        "has_join": " join " in wrapped,
        "has_group_by": " group by " in wrapped,
        "has_union_all": " union all " in wrapped,
        "has_lateral_view": " lateral view " in wrapped,
        "has_map": re.search(r"\bmap\s*\(", normalized) is not None,
        "has_grouping_sets": " grouping sets " in wrapped,
    }


def detect_text_warnings(sql: str) -> list[str]:
    warnings: list[str] = []
    if "\u3000" in sql:
        warnings.append("检测到全角空格。")
    if "\u00a0" in sql:
        warnings.append("检测到不间断空格。")
    return warnings


def mark_cte_relations(result: SQLAnalysisResult) -> None:
    cte_names = set(result.ctes.keys())
    for cte in result.ctes.values():
        for relation in cte.referenced_relations:
            relation.relation_type = "cte" if relation.relation_name in cte_names else "physical_table"
    for statement in result.statements:
        for relation in statement.source_relations:
            relation.relation_type = "cte" if relation.relation_name in cte_names else "physical_table"
