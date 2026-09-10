SET odps.sql.type.system.odps2 = true;
SET odps.sql.groupby.skewindata = true;


WITH report_rows AS (
    SELECT
        row_no,
        dimension_type,
        dimension_value
    FROM VALUES
        (1, 'region', 'south'),
        (2, 'region', 'north'),
        (3, 'product', 'loan'),
        (4, 'product', 'deposit')
    AS t(
        row_no,
        dimension_type,
        dimension_value
    )
),

report_row_count AS (
    SELECT
        COUNT(*) AS row_count
    FROM report_rows
),

base AS (
    SELECT
        customer_id,
        region,
        product,
        amount,
        tags,
        batch_num
    FROM fact_sales
    WHERE dt = '${p_month}'
),

customer_enriched AS (
    SELECT /*+ MAPJOIN(d) */
        b.customer_id,
        d.customer_name,
        b.region,
        b.product,
        b.amount,
        b.tags,
        b.batch_num
    FROM base b
    LEFT JOIN dim_customer d
        ON b.customer_id = d.customer_id
),

exploded AS (
    SELECT
        customer_id,
        customer_name,
        region,
        product,
        amount,
        batch_num,
        tag
    FROM customer_enriched
    LATERAL VIEW
        EXPLODE(
            SPLIT(tags, ',')
        ) exploded_tags AS tag
),

preagg AS (
    SELECT
        region,
        product,
        batch_num,
        SUM(amount) AS total_amount
    FROM exploded
    GROUP BY
        region,
        product,
        batch_num
),

grouped AS (
    SELECT
        region,
        product,
        batch_num,
        SUM(total_amount) AS total_amount
    FROM preagg
    GROUP BY GROUPING SETS (
        (region, product, batch_num),
        (region, batch_num),
        (batch_num)
    )
),

unioned AS (
    SELECT
        region,
        product,
        batch_num,
        total_amount
    FROM grouped
    WHERE product IS NOT NULL

    UNION ALL

    SELECT
        region,
        product,
        batch_num,
        total_amount
    FROM grouped
    WHERE product IS NULL
)

INSERT OVERWRITE TABLE production_result
PARTITION(
    dt = '${p_month}',
    batch_num
)
SELECT
    COALESCE(u.region, 'ALL') AS region,
    COALESCE(u.product, 'ALL') AS product,
    u.total_amount,
    u.batch_num
FROM unioned u
CROSS JOIN report_row_count r
WHERE r.row_count = 4
;


WITH base_tags AS (
    SELECT
        customer_id,
        tags,
        batch_num
    FROM fact_sales
    WHERE dt = '${p_month}'
),

exploded_tags AS (
    SELECT
        customer_id,
        batch_num,
        tag
    FROM base_tags
    LATERAL VIEW
        EXPLODE(
            SPLIT(tags, ',')
        ) exploded AS tag
)

INSERT OVERWRITE TABLE production_tag_result
PARTITION(
    dt = '${p_month}',
    batch_num
)
SELECT
    tag,
    COUNT(*) AS cnt,
    batch_num
FROM exploded_tags
GROUP BY
    tag,
    batch_num
;