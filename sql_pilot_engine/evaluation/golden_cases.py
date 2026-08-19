from __future__ import annotations

from sql_pilot_engine.evaluation.models import (
    ExpectedAgentBehavior,
    GoldenTextToSQLCase,
)


TEXT_TO_SQL_GOLDEN_V0_1 = (

    # ========================================================
    # ANSWER
    # ========================================================

    GoldenTextToSQLCase(
        case_id=(
            "tech_high_tech_balance_current"
        ),

        question=(
            "统计下本期高新技术企业的贷款余额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_101_cldwdk",
        ),

        expected_dimensions=(
            "dt",
        ),

        expected_metrics=(
            "tech_loan_balance",
        ),

        expected_filters=(
            "is_high_tech_ent_loan_code = '1'",
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "dt",
        ),
        

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "tech_sci_medium_enterprise_count_current"
        ),

        question=(
            "统计下本期科技中小企业的获贷企业数"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_101_cldwdk",
        ),

        expected_dimensions=(
            "dt",
        ),

        expected_metrics=(
            "tech_loan_enterprise_count",
        ),

        expected_filters=(
            "is_sci_medium_ent_loan_code = '1'",
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "dt",
        ),

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id="green_balance_current",

        question=(
            "统计本期绿色贷款余额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=(
            "dt",
        ),

        expected_metrics=(
            "green_loan_balance",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "dt",
        ),

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "green_enterprise_count_current"
        ),

        question=(
            "统计本期绿色贷款获贷企业数"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=(
            "dt",
        ),

        expected_metrics=(
            "green_loan_enterprise_count",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "dt",
        ),

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id="tech_by_area_current",

        question=(
            "按地区统计本期科技贷款余额、"
            "获贷企业数和加权利率"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_101_cldwdk",
        ),

        expected_dimensions=(
            "fin_org_branch_area_code",
        ),

        require_dimension_match=True,
        require_group_by_match=True,

        expected_metrics=(
            "tech_loan_balance",
            "tech_loan_enterprise_count",
            "tech_loan_weighted_rate",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "fin_org_branch_area_code",
        ),

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id="green_by_org_type_current",

        question=(
            "按机构类型统计本期绿色贷款余额、"
            "获贷企业数和加权利率"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=(
            "fin_org_type_code",
        ),

        expected_metrics=(
            "green_loan_balance",
            "green_loan_enterprise_count",
            "green_loan_weighted_rate",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "fin_org_type_code",
        ),
        require_dimension_match=True,
        require_group_by_match=True,
        expected_trusted_sql=True,
    ),

    # ========================================================
    # CLARIFY
    # ========================================================

    GoldenTextToSQLCase(
        case_id=(
            "ambiguous_loan_balance_current"
        ),

        question=(
            "统计本期贷款余额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.CLARIFY
        ),

        expected_trusted_sql=False,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "tech_balance_yoy_mom_missing_context"
        ),

        question=(
            "统计高新技术企业的贷款余额同比及环比情况"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.CLARIFY
        ),

        expected_trusted_sql=False,
    ),
    
    GoldenTextToSQLCase(
        case_id=(
            "green_weighted_rate_current"
        ),

        question=(
            "统计本期绿色贷款加权利率"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_metrics=(
            "green_loan_weighted_rate",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "green_balance_and_count_current"
        ),

        question=(
            "统计本期绿色贷款余额和获贷企业数"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_metrics=(
            "green_loan_balance",
            "green_loan_enterprise_count",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "green_count_by_org_type"
        ),

        question=(
            "按机构类型统计本期绿色贷款获贷企业数"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=(
            "fin_org_type_code",
        ),

        expected_metrics=(
            "green_loan_enterprise_count",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "fin_org_type_code",
        ),

        require_dimension_match=True,
        require_group_by_match=True,

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "tech_balance_by_area"
        ),

        question=(
            "按地区统计本期科技贷款余额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_101_cldwdk",
        ),

        expected_dimensions=(
            "fin_org_branch_area_code",
        ),

        expected_metrics=(
            "tech_loan_balance",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "fin_org_branch_area_code",
        ),

        require_dimension_match=True,
        require_group_by_match=True,

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "tech_balance_current"
        ),

        question=(
            "统计本期科技贷款余额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_101_cldwdk",
        ),

        expected_metrics=(
            "tech_loan_balance",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_trusted_sql=True,
    ),

    GoldenTextToSQLCase(
        case_id=(
            "green_synonym_balance_current"
        ),

        question=(
            "查询当前期绿色单位贷款余额"
        ),

        expected_behavior=(
            ExpectedAgentBehavior.ANSWER
        ),

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_metrics=(
            "green_loan_balance",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_trusted_sql=True,
    ),
)