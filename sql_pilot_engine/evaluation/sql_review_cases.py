from __future__ import annotations

from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class SQLReviewGoldenCase:
    """
    SQL Review Capability 的 Golden Case。

    只描述公共 Capability 行为，
    不依赖 ReviewService / RuleRegistry
    等内部实现。
    """

    case_id: str
    description: str

    sql: str

    expected_success: bool
    expect_trusted_sql: bool

    expected_statuses: tuple[
        str,
        ...,
    ] = ()

    expected_rule_ids: tuple[
        str,
        ...,
    ] = ()

    expect_fix_applied: (
        bool | None
    ) = None

    expect_issues: (
        bool | None
    ) = None


SQL_REVIEW_GOLDEN_CASES: tuple[
    SQLReviewGoldenCase,
    ...,
] = (

    # ========================================================
    # 1. Normal SELECT
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_normal_select",
        description=(
            "真实表上的普通 SELECT "
            "应产生 Trusted SQL。"
        ),
        sql="""
        SELECT
            loan_bal_rmb,
            dt
        FROM
            odps_prd_dwd.ods_hd_100_cldkxx
        WHERE
            dt = '202607'
        """.strip(),
        expected_success=True,
        expect_trusted_sql=True,
        expected_statuses=(
            "no_issue",
            "fix_verified",
            "fixed",
        ),
    ),

    # ========================================================
    # 2. Aggregate
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_aggregate",
        description=(
            "正常聚合 SQL 应通过可信审查。"
        ),
        sql="""
        SELECT
            dt,
            SUM(
                loan_bal_rmb
            ) AS total_loan_balance
        FROM
            odps_prd_dwd.ods_hd_100_cldkxx
        WHERE
            dt = '202607'
        GROUP BY
            dt
        """.strip(),
        expected_success=True,
        expect_trusted_sql=True,
    ),

    # ========================================================
    # 3. CTE
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_cte",
        description=(
            "合法 CTE SQL 应通过解析、"
            "Metadata 和 Review。"
        ),
        sql="""
        WITH loan_data AS (
            SELECT
                loan_bal_rmb,
                dt
            FROM
                odps_prd_dwd.ods_hd_100_cldkxx
            WHERE
                dt = '202607'
        )
        SELECT
            SUM(
                loan_bal_rmb
            ) AS total_loan_balance
        FROM
            loan_data
        """.strip(),
        expected_success=True,
        expect_trusted_sql=True,
    ),

    # ========================================================
    # 4. JOIN
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_join",
        description=(
            "合法 JOIN 应能正确识别"
            "表别名和字段引用。"
        ),
        sql="""
        SELECT
            a.dt
        FROM
            odps_prd_dwd.ods_hd_100_cldkxx a
        JOIN
            odps_prd_dwd.ods_hd_100_cldkxx b
            ON a.dt = b.dt
        WHERE
            a.dt = '202607'
        """.strip(),
        expected_success=True,
        expect_trusted_sql=True,
    ),

    # ========================================================
    # 5. Missing Table
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_missing_table",
        description=(
            "不存在的物理表不能产生 Trusted SQL。"
        ),
        sql="""
        SELECT
            id
        FROM
            odps_prd_dwd.table_that_does_not_exist
        """.strip(),
        expected_success=False,
        expect_trusted_sql=False,
        expect_issues=True,
    ),

    # ========================================================
    # 6. Missing Column
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_missing_column",
        description=(
            "真实表中不存在的字段"
            "必须被 Metadata Validation 阻断。"
        ),
        sql="""
        SELECT
            this_column_does_not_exist
        FROM
            odps_prd_dwd.ods_hd_100_cldkxx
        """.strip(),
        expected_success=False,
        expect_trusted_sql=False,
        expect_issues=True,
    ),

    # ========================================================
    # 7. Dangerous DROP
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_drop_blocked",
        description=(
            "DROP 必须被安全规则主动阻断，"
            "不能产生 Trusted SQL。"
        ),
        sql="""
        DROP TABLE
            odps_prd_dwd.ods_hd_100_cldkxx
        """.strip(),
        expected_success=False,
        expect_trusted_sql=False,
        expect_issues=True,
    ),

    # ========================================================
    # 8. Syntax Error
    # ========================================================

    SQLReviewGoldenCase(
        case_id="review_invalid_sql",
        description=(
            "无法解析的 SQL 不能产生 Trusted SQL。"
        ),
        sql="""
        SELECT
            FROM
        """.strip(),
        expected_success=False,
        expect_trusted_sql=False,
    ),
)