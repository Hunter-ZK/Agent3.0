from sql_pilot_engine.analysis import (
    SQLParser,
    SQLScopeAnalyzer,
    ScopeKind,
    ScopeSourceKind,
)


def analyze(sql: str):
    parser = SQLParser()
    analyzer = SQLScopeAnalyzer()

    parse_result = parser.parse(sql)

    assert parse_result.success is True

    return analyzer.analyze(
        parse_result=parse_result
    )


def test_simple_table_scope():
    result = analyze(
        """
        SELECT
            o.user_id,
            o.order_amount
        FROM dwd_order_detail o
        """
    )

    assert len(result.scopes) == 1

    root = result.scopes[0]
    print(root)
    assert root.kind == ScopeKind.ROOT

    assert len(root.sources) == 1

    source = root.sources[0]
    print(source.kind)
    assert (
        source.kind
        == ScopeSourceKind.PHYSICAL_TABLE
    )
    assert (
        source.physical_name
        == "dwd_order_detail"
    )
    assert source.name == "o"


def test_cte_creates_independent_scope():
    result = analyze(
        """
        WITH order_summary AS (
            SELECT
                user_id,
                SUM(order_amount)
                    AS total_amount
            FROM dwd_order_detail
            GROUP BY user_id
        )
        SELECT
            o.user_id,
            o.total_amount
        FROM order_summary o
        """
    )

    assert len(result.scopes) == 2

    cte_scope = next(
        scope
        for scope in result.scopes
        if scope.kind == ScopeKind.CTE
    )

    root_scope = next(
        scope
        for scope in result.scopes
        if scope.kind == ScopeKind.ROOT
    )

    assert set(
        cte_scope.output_columns
    ) == {
        "user_id",
        "total_amount",
    }

    cte_source = next(
        source
        for source in root_scope.sources
        if source.name == "o"
    )

    assert (
        cte_source.kind
        == ScopeSourceKind.CTE
    )

    assert (
        cte_source.source_scope_id
        == cte_scope.scope_id
    )


def test_derived_table_hides_inner_table():
    result = analyze(
        """
        SELECT
            s.user_id
        FROM (
            SELECT
                o.user_id
            FROM dwd_order_detail o
        ) s
        """
    )

    derived_scope = next(
        scope
        for scope in result.scopes
        if scope.kind
        == ScopeKind.DERIVED_TABLE
    )

    root_scope = next(
        scope
        for scope in result.scopes
        if scope.kind == ScopeKind.ROOT
    )

    root_source = next(
        source
        for source in root_scope.sources
        if source.name == "s"
    )

    assert (
        root_source.kind
        == ScopeSourceKind.DERIVED_TABLE
    )

    assert (
        root_source.source_scope_id
        == derived_scope.scope_id
    )

    assert (
        "user_id"
        in derived_scope.output_columns
    )

    assert all(
        source.physical_name
        != "dwd_order_detail"
        for source in root_scope.sources
    )


def test_same_column_can_exist_in_different_scopes():
    result = analyze(
        """
        WITH t AS (
            SELECT user_id
            FROM dwd_order_detail
        )
        SELECT t.user_id
        FROM t
        """
    )

    cte_scope = next(
        scope
        for scope in result.scopes
        if scope.kind == ScopeKind.CTE
    )

    root_scope = next(
        scope
        for scope in result.scopes
        if scope.kind == ScopeKind.ROOT
    )

    assert any(
        column.name == "user_id"
        for column in cte_scope.columns
    )

    assert any(
        column.name == "user_id"
        and column.qualifier == "t"
        for column in root_scope.columns
    )