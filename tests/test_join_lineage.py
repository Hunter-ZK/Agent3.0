from sql_pilot_engine.analysis import (
    SQLJoinAnalyzer,
    SQLLineageAnalyzer,
    SQLParser,
    SQLScopeAnalyzer,
    ScopeKind,
)


def build_analysis(sql: str):
    parser = SQLParser()
    scope_analyzer = SQLScopeAnalyzer()

    parse_result = parser.parse(sql)

    assert parse_result.success is True

    scope_analysis = scope_analyzer.analyze(
        parse_result=parse_result
    )

    return parse_result, scope_analysis


def test_join_structure():
    sql = """
    SELECT
        o.user_id,
        u.user_name
    FROM dwd_order_detail o
    LEFT JOIN dim_user u
      ON o.user_id = u.user_id
    """

    parse_result, scope_analysis = (
        build_analysis(sql)
    )

    result = SQLJoinAnalyzer().analyze(
        parse_result=parse_result,
        scope_analysis=scope_analysis,
    )

    assert len(result.joins) == 1

    join = result.joins[0]

    assert join.left_sources == ("o",)
    assert join.right_source == "u"
    assert join.join_type == "LEFT"
    assert join.has_condition is True


def test_cte_lineage_reaches_physical_column():
    sql = """
    WITH order_summary AS (
        SELECT
            user_id,
            SUM(order_amount)
                AS total_amount
        FROM dwd_order_detail
        GROUP BY user_id
    )
    SELECT
        o.total_amount
    FROM order_summary o
    """

    _, scope_analysis = build_analysis(sql)

    lineage = SQLLineageAnalyzer().analyze(
        scope_analysis
    )

    root_scope = next(
        scope
        for scope in scope_analysis.scopes
        if scope.kind == ScopeKind.ROOT
    )

    total_amount = next(
        item
        for item in lineage.columns
        if (
            item.scope_id
            == root_scope.scope_id
            and item.output_column
            == "total_amount"
        )
    )

    assert len(
        total_amount.physical_sources
    ) == 1

    source = (
        total_amount.physical_sources[0]
    )

    assert (
        source.table_name
        == "dwd_order_detail"
    )

    assert (
        source.column_name
        == "order_amount"
    )


def test_unqualified_column_is_not_guessed():
    sql = """
    SELECT user_id
    FROM dwd_order_detail o
    JOIN dim_user u
      ON o.user_id = u.user_id
    """

    _, scope_analysis = build_analysis(sql)

    lineage = SQLLineageAnalyzer().analyze(
        scope_analysis
    )

    root_scope = next(
        scope
        for scope in scope_analysis.scopes
        if scope.kind == ScopeKind.ROOT
    )

    result = next(
        item
        for item in lineage.columns
        if (
            item.scope_id
            == root_scope.scope_id
            and item.output_column
            == "user_id"
        )
    )

    assert result.physical_sources == ()

    assert (
        "ambiguous:user_id"
        in result.unresolved_references
    )