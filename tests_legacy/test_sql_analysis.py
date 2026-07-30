from sql_pilot_engine.analysis.analyzer import analyze_sql


def test_analyze_sql_should_detect_multiple_statements():
    sql = """
    set odps.instance.priority=7;
    insert overwrite table dws_user_trade_summary
    select user_id from dwd_user_order_detail;
    """
    analysis = analyze_sql(sql)
    assert len(analysis.statements) == 2
    assert analysis.file_features["has_multiple_statements"] is True
    assert analysis.file_features["has_insert"] is True


def test_analyze_sql_should_extract_cte():
    sql = """
    with a as (
        select user_id, pay_amount
        from dwd_user_order_detail
    )
    select user_id from a
    """
    analysis = analyze_sql(sql)
    assert "a" in analysis.ctes
    assert "user_id" in analysis.ctes["a"].output_columns
    assert analysis.file_features["has_cte"] is True


def test_analyze_sql_should_detect_complex_features():
    sql = """
    select a.user_id, sum(a.pay_amount)
    from dwd_user_order_detail a
    join dim_city b on a.city_id = b.city_id
    group by a.user_id
    """
    analysis = analyze_sql(sql)
    assert analysis.file_features["has_join"] is True
    assert analysis.file_features["has_group_by"] is True


def test_analyze_sql_should_support_project_table_name():
    sql = "select user_id from odps_prd_ods.ods_user_order_detail"
    analysis = analyze_sql(sql)
    relations = analysis.statements[0].source_relations
    assert relations[0].relation_name == "odps_prd_ods.ods_user_order_detail"
