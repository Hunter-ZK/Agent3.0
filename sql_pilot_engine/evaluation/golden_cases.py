from __future__ import annotations

from sql_pilot_engine.evaluation.models import (
    GoldenTextToSQLCase,
)


TEXT_TO_SQL_GOLDEN_V0_1 = (

    # =========================================================
    # L2：科技贷款 + 指标 + 企业类型Filter
    # =========================================================

    GoldenTextToSQLCase(
        case_id="tech_high_tech_balance_current",

        question="统计下本期高新技术企业的贷款余额",

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
    ),

    GoldenTextToSQLCase(
        case_id="tech_sci_medium_enterprise_count_current",

        question="统计下本期科技中小企业的获贷企业数",

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
    ),

    # =========================================================
    # L2：业务主题识别
    # =========================================================

    GoldenTextToSQLCase(
        case_id="green_balance_current",

        question="统计本期绿色贷款余额",

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
    ),

    GoldenTextToSQLCase(
        case_id="green_enterprise_count_current",

        question="统计本期绿色贷款获贷企业数",

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
    ),

    # =========================================================
    # L3：维度 + 多指标
    # =========================================================

    GoldenTextToSQLCase(
        case_id="tech_by_area_current",

        question="按地区统计本期科技贷款情况",

        expected_tables=(
            "dwd_hd_101_cldwdk",
        ),

        expected_dimensions=(
            "fin_org_branch_area_code",
            "dt",
        ),

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
            "dt",
        ),
    ),

    GoldenTextToSQLCase(
        case_id="green_by_org_type_current",

        question="按机构类型统计本期绿色贷款情况",

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=(
            "fin_org_type_code",
            "dt",
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
            "dt",
        ),
    ),

    # =========================================================
    # L3：业务主题 + 企业类型 + 分组
    # =========================================================

    GoldenTextToSQLCase(
        case_id="high_tech_by_org_type_current",

        question="分机构类型统计本期高新技术企业贷款情况",

        expected_tables=(
            "dwd_hd_101_cldwdk",
        ),

        expected_dimensions=(
            "fin_org_type_code",
            "dt",
        ),

        expected_metrics=(
            "tech_loan_balance",
            "tech_loan_enterprise_count",
            "tech_loan_weighted_rate",
        ),

        expected_filters=(
            "is_high_tech_ent_loan_code = '1'",
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "fin_org_type_code",
            "dt",
        ),
    ),

    GoldenTextToSQLCase(
        case_id="green_balance_by_type_current",

        question="按绿色贷款类型统计本期绿色贷款余额",

        expected_tables=(
            "dwd_hd_201_cldwdk",
        ),

        expected_dimensions=(
            "green_loan_type_code",
            "dt",
        ),

        expected_metrics=(
            "green_loan_balance",
        ),

        expected_filters=(
            "dt = '${p_month_yyyymm}'",
        ),

        expected_group_by=(
            "green_loan_type_code",
            "dt",
        ),
    ),
)