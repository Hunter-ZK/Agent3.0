from __future__ import annotations

from sql_pilot_engine.evaluation.text_to_sql.models import (
    TextToSQLEvalCase,
)


TEXT_TO_SQL_V2_CASES = (

    # ========================================================
    # A. 科技贷款 / 高新技术企业
    # ========================================================

    TextToSQLEvalCase(
        case_id=(
            "explicit_high_tech_month"
        ),
        question=(
            "统计2026年7月高新技术企业的贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_balance",
        ),
        required_filter_terms=(
            "is_high_tech_mfg_loan_code",
            "202607",
        ),
    ),

    TextToSQLEvalCase(
        case_id="current_high_tech",
        question=(
            "统计本期高新技术企业的贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_balance",
        ),
        required_filter_terms=(
            "is_high_tech_mfg_loan_code",
            "p_month_yyyymm",
        ),
    ),

    TextToSQLEvalCase(
        case_id="high_tech_yoy",
        question=(
            "统计高新技术企业贷款余额同比"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_balance",
        ),
        required_filter_terms=(
            "is_high_tech_mfg_loan_code",
        ),
    ),

    TextToSQLEvalCase(
        case_id="high_tech_mom",
        question=(
            "统计高新技术企业贷款余额环比"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_balance",
        ),
        required_filter_terms=(
            "is_high_tech_mfg_loan_code",
        ),
    ),

    # ========================================================
    # B. 绿色贷款
    # ========================================================

    TextToSQLEvalCase(
        case_id="green_current",
        question=(
            "统计本期绿色贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_balance",
        ),
        required_filter_terms=(
            "p_month_yyyymm",
        ),
    ),

    TextToSQLEvalCase(
        case_id="green_month",
        question=(
            "统计2026年7月绿色贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_balance",
        ),
        required_filter_terms=(
            "202607",
        ),
    ),

    # ========================================================
    # C. 企业数量
    # ========================================================

    TextToSQLEvalCase(
        case_id="tech_enterprise_count",
        question=(
            "统计本期科技贷款获贷企业数"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_enterprise_count",
        ),
    ),

    TextToSQLEvalCase(
        case_id="green_enterprise_count",
        question=(
            "统计本期绿色贷款获贷企业数"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_enterprise_count",
        ),
    ),

    # ========================================================
    # D. 加权利率
    # ========================================================

    TextToSQLEvalCase(
        case_id="tech_weighted_rate",
        question=(
            "统计本期科技贷款加权利率"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_weighted_rate",
        ),
    ),

    TextToSQLEvalCase(
        case_id="green_weighted_rate",
        question=(
            "统计本期绿色贷款加权利率"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_weighted_rate",
        ),
    ),

    # ========================================================
    # E. 分组分析
    # ========================================================

    TextToSQLEvalCase(
        case_id="tech_balance_by_region",
        question=(
            "统计本期各地区科技贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_balance",
        ),
        expected_dimensions=(
            "fin_org_branch_area_code",
        ),
        expected_group_by=(
            "fin_org_branch_area_code",
        ),
    ),

    TextToSQLEvalCase(
        case_id="green_balance_by_region",
        question=(
            "统计本期各地区绿色贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_balance",
        ),
        expected_dimensions=(
            "fin_org_branch_area_code",
        ),
        expected_group_by=(
            "fin_org_branch_area_code",
        ),
    ),

    TextToSQLEvalCase(
        case_id="tech_balance_by_org_type",
        question=(
            "统计本期各金融机构类型科技贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_balance",
        ),
        expected_dimensions=(
            "fin_org_type_code",
        ),
        expected_group_by=(
            "fin_org_type_code",
        ),
    ),

    TextToSQLEvalCase(
        case_id="green_balance_by_org_type",
        question=(
            "统计本期各金融机构类型绿色贷款余额"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_balance",
        ),
        expected_dimensions=(
            "fin_org_type_code",
        ),
        expected_group_by=(
            "fin_org_type_code",
        ),
    ),

    # ========================================================
    # F. 业务歧义 / Clarification
    # ========================================================

    TextToSQLEvalCase(
        case_id="ambiguous_current_balance",
        question=(
            "统计本期贷款余额"
        ),
        expected_initial=(
            "clarification"
        ),
        clarification_answer=(
            "绿色贷款"
        ),
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_balance",
        ),
    ),

    TextToSQLEvalCase(
        case_id="ambiguous_balance",
        question=(
            "统计贷款余额"
        ),
        expected_initial=(
            "clarification"
        ),
        clarification_answer=(
            "高新技术企业贷款"
        ),
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_balance",
        ),
        required_filter_terms=(
            "is_high_tech_mfg_loan_code",
        ),
    ),

    TextToSQLEvalCase(
        case_id="ambiguous_enterprise_count",
        question=(
            "统计本期获贷企业数"
        ),
        expected_initial=(
            "clarification"
        ),
        clarification_answer=(
            "绿色贷款"
        ),
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_enterprise_count",
        ),
    ),

    TextToSQLEvalCase(
        case_id="ambiguous_rate",
        question=(
            "统计本期贷款利率"
        ),
        expected_initial=(
            "clarification"
        ),
        clarification_answer=(
            "科技贷款"
        ),
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_weighted_rate",
        ),
    ),

    # ========================================================
    # G. 指标 + 维度组合
    # ========================================================

    TextToSQLEvalCase(
        case_id=(
            "green_enterprise_count_by_region"
        ),
        question=(
            "统计2026年7月各地区绿色贷款获贷企业数"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_200_cldkxx",
        ),
        expected_metrics=(
            "green_loan_enterprise_count",
        ),
        expected_dimensions=(
            "fin_org_branch_area_code",
        ),
        expected_group_by=(
            "fin_org_branch_area_code",
        ),
        required_filter_terms=(
            "202607",
        ),
    ),

    TextToSQLEvalCase(
        case_id=(
            "tech_rate_by_org_type"
        ),
        question=(
            "统计本期各金融机构类型科技贷款加权利率"
        ),
        expected_initial="result",
        expected_tables=(
            "ods_hd_100_cldkxx",
        ),
        expected_metrics=(
            "tech_loan_weighted_rate",
        ),
        expected_dimensions=(
            "fin_org_type_code",
        ),
        expected_group_by=(
            "fin_org_type_code",
        ),
    ),
)