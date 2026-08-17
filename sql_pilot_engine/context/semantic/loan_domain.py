from __future__ import annotations

from sql_pilot_engine.context.models import (
    ContextDocument,
    ContextDocumentKind,
)


LOAN_DOMAIN_CONTEXT_DOCUMENTS = (
    # =========================================================
    # Business Knowledge
    # =========================================================

    ContextDocument(
        document_id="loan_snapshot_balance_rule",
        kind=ContextDocumentKind.BUSINESS_KNOWLEDGE,
        text=(
            "贷款余额属于时点存量指标。"
            "统计某一期贷款余额时，应限定对应的 dt。"
            "不同 dt 的贷款余额不得直接相加。"
        ),
        metadata={
            "domain": "loan",
            "topic": "balance",
        },
    ),

    ContextDocument(
        document_id="loan_enterprise_count_rule",
        kind=ContextDocumentKind.BUSINESS_KNOWLEDGE,
        text=(
            "获贷企业数必须使用 "
            "COUNT(DISTINCT ent_code) 计算。"
            "不同分组下的获贷企业数不能直接相加"
            "得到总体企业数。"
        ),
        metadata={
            "domain": "loan",
            "topic": "enterprise_count",
        },
    ),

    ContextDocument(
        document_id="loan_weighted_rate_rule",
        kind=ContextDocumentKind.BUSINESS_KNOWLEDGE,
        text=(
            "贷款存量利率使用贷款余额加权计算："
            "SUM(loan_bal_rmb * rate) "
            "/ SUM(loan_bal_rmb)。"
        ),
        metadata={
            "domain": "loan",
            "topic": "rate",
        },
    ),

    ContextDocument(
        document_id="tech_loan_subject_rule",
        kind=ContextDocumentKind.BUSINESS_KNOWLEDGE,
        text=(
            "科技贷款业务使用表 "
            "dwd_hd_101_cldwdk。"
            "高新技术企业贷款条件为 "
            "is_high_tech_ent_loan_code = '1'；"
            "科技中小企业贷款条件为 "
            "is_sci_medium_ent_loan_code = '1'。"
        ),
        metadata={
            "domain": "tech_loan",
            "topic": "subject_mapping",
        },
    ),

    ContextDocument(
        document_id="green_loan_subject_rule",
        kind=ContextDocumentKind.BUSINESS_KNOWLEDGE,
        text=(
            "绿色贷款或绿色单位贷款业务使用表 "
            "dwd_hd_201_cldwdk。"
            "如用户指定绿色贷款类型，"
            "应使用 green_loan_type_code 增加过滤条件。"
        ),
        metadata={
            "domain": "green_loan",
            "topic": "subject_mapping",
        },
    ),

    # =========================================================
    # Verified SQL
    # 只放已经能够确认业务口径的SQL
    # =========================================================

    ContextDocument(
        document_id="verified_high_tech_loan_balance",
        kind=ContextDocumentKind.VERIFIED_SQL,
        text=(
            "问题：统计下本期高新技术企业的贷款余额。\n"
            "SQL："
            "SELECT SUM(loan_bal_rmb) AS loan_bal_rmb, dt "
            "FROM odps_prd_dwd.dwd_hd_101_cldwdk "
            "WHERE is_high_tech_ent_loan_code = '1' "
            "AND dt = '${p_month_yyyymm}' "
            "GROUP BY dt"
        ),
        metadata={
            "domain": "tech_loan",
            "topic": "high_tech_balance",
        },
    ),

    ContextDocument(
        document_id="verified_sci_medium_ent_count",
        kind=ContextDocumentKind.VERIFIED_SQL,
        text=(
            "问题：统计下本期科技中小企业的获贷企业数。\n"
            "SQL："
            "SELECT COUNT(DISTINCT ent_code) AS ent_num, dt "
            "FROM odps_prd_dwd.dwd_hd_101_cldwdk "
            "WHERE is_sci_medium_ent_loan_code = '1' "
            "AND dt = '${p_month_yyyymm}' "
            "GROUP BY dt"
        ),
        metadata={
            "domain": "tech_loan",
            "topic": "sci_medium_enterprise_count",
        },
    ),
)