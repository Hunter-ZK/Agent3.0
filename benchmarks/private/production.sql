set odps.instance.priority=7;
set odps.sql.mapper.split.size=32;
set odps.sql.decimal.odps2=true;
set odps.sql.groupby.skewindata=true;
set odps.sql.reshuffle.dynamicpt=false;
set odps.optimizer.cbo.rule.enable.aggregate.groupingsets.expand=true;

WITH pjrz_type AS (
    SELECT * FROM VALUES
    (1,'pjrz','合计','票据融资合计','票据融资合计'),
    (2,'pjrz','合计','合计','按币种分类：'),
    (3,'pjrz','curr_code','CNY','  人民币'),
    (4,'pjrz','curr_code','~CNY','  外币'),
    (5,'pjrz','curr_code','NULL','  未填报'),
    (6,'pjrz','合计','合计','按贴现币种分类：'),
    (7,'pjrz','discount_curr_code','CNY','  人民币'),
    (8,'pjrz','discount_curr_code','~CNY','  外币'),
    (9,'pjrz','discount_curr_code','NULL','  未填报'),
    (10,'pjrz','合计','合计','按贴现方式分类：'),
    (11,'pjrz','discount_type_code','01','  直贴'),
    (12,'pjrz','discount_type_code','02','  买断式转贴现'),
    (13,'pjrz','discount_type_code','09','  其他'),
    (14,'pjrz','discount_type_code','NULL','  未填报'),
    (15,'pjrz','合计','合计','按票据种类分类：'),
    (16,'pjrz','bill_type_code','01','  银行承兑汇票'),
    (17,'pjrz','bill_type_code','02','  商业承兑汇票'),
    (18,'pjrz','bill_type_code','03','  财务公司承兑汇票'),
    (19,'pjrz','bill_type_code','NULL','  未填报'),
    (20,'pjrz','合计','合计','按贴现申请人证件分类：'),
    (21,'pjrz','discount_card_type_code_lv1','A','  单位'),
    (22,'pjrz','discount_card_type_code','A01','   其中：统一社会信用代码'),
    (23,'pjrz','discount_card_type_code','A02','        组织机构代码'),
    (24,'pjrz','discount_card_type_code','A03','        其他'),
    (25,'pjrz','discount_card_type_code_lv1','B','  自然人'),
    (26,'pjrz','discount_card_type_code','B01','   其中：身份证'),
    (27,'pjrz','discount_card_type_code','~B01','        其他证件'),
    (28,'pjrz','discount_card_type_code_lv1','C','  资管产品'),
    (29,'pjrz','discount_card_type_code','C01','   其中：资管产品统计编码'),
    (30,'pjrz','discount_card_type_code','C02','     资管产品登记备案编码'),
    (31,'pjrz','discount_card_type_code_lv1','L01','  全球法人识别编码（LEI码）'),
    (32,'pjrz','discount_card_type_code_lv1','Z99','  自定义码'),
    (33,'pjrz','discount_card_type_code_lv1','NULL','  未填报'),
    (34,'pjrz','合计','合计','按贴现申请人部门分类：'),
    (35,'pjrz','discount_eco_sector_code','A','  广义政府'),
    (36,'pjrz','discount_eco_sector_code','B','  金融机构部门'),
    (37,'pjrz','discount_eco_sector_code','C','  非金融企业部门'),
    (38,'pjrz','discount_eco_sector_code','D','  住户部门'),
    (39,'pjrz','discount_eco_sector_code','E','  非居民部门'),
    (40,'pjrz','discount_eco_sector_code','NULL','  未填报'),
    (41,'pjrz','合计','合计','按贴现申请人经济成分分类：'),
    (42,'pjrz','discount_ent_eco_elem_code','A01','  国有控股企业'),
    (43,'pjrz','discount_ent_eco_elem_code','A02','  集体控股企业'),
    (44,'pjrz','discount_ent_eco_elem_code','B01','  私人控股企业'),
    (45,'pjrz','discount_ent_eco_elem_code','B02','  港澳台商控股企业'),
    (46,'pjrz','discount_ent_eco_elem_code','B03','  外商控股企业'),
    (47,'pjrz','discount_ent_eco_elem_code','NULL','  未填报'),
    (48,'pjrz','合计','合计','按贴现申请人规模分类：'),
    (49,'pjrz','discount_ent_scale_code','CS01','  大型'),
    (50,'pjrz','discount_ent_scale_code','CS02','  中型'),
    (51,'pjrz','discount_ent_scale_code','CS03','  小型'),
    (52,'pjrz','discount_ent_scale_code','CS04','  微型'),
    (53,'pjrz','discount_ent_scale_code','CS05','  其他'),
    (54,'pjrz','discount_ent_scale_code','NULL','  未填报'),
    (55,'pjrz','合计','合计','按承兑人证件分类：'),
    (56,'pjrz','accept_card_type_code_lv1','A','  单位'),
    (57,'pjrz','accept_card_type_code','A01','   其中：统一社会信用代码'),
    (58,'pjrz','accept_card_type_code','A02','        组织机构代码'),
    (59,'pjrz','accept_card_type_code','A03','        其他'),
    (60,'pjrz','accept_card_type_code_lv1','B','  自然人'),
    (61,'pjrz','accept_card_type_code','B01','   其中：身份证'),
    (62,'pjrz','accept_card_type_code','~B01','        其他证件'),
    (63,'pjrz','accept_card_type_code_lv1','C','  资管产品'),
    (64,'pjrz','accept_card_type_code','C01','   其中：资管产品统计编码'),
    (65,'pjrz','accept_card_type_code','C02','     资管产品登记备案编码'),
    (66,'pjrz','accept_card_type_code_lv1','L01','  全球法人识别编码（LEI码）'),
    (67,'pjrz','accept_card_type_code_lv1','Z99','  自定义码'),
    (68,'pjrz','accept_card_type_code_lv1','NULL','  未填报'),
    (69,'pjrz','合计','合计','按出票人证件分类：'),
    (70,'pjrz','drawer_card_type_code_lv1','A','  单位'),
    (71,'pjrz','drawer_card_type_code','A01','   其中：统一社会信用代码'),
    (72,'pjrz','drawer_card_type_code','A02','        组织机构代码'),
    (73,'pjrz','drawer_card_type_code','A03','        其他'),
    (74,'pjrz','drawer_card_type_code_lv1','B','  自然人'),
    (75,'pjrz','drawer_card_type_code','B01','   其中：身份证'),
    (76,'pjrz','drawer_card_type_code','~B01','        其他证件'),
    (77,'pjrz','drawer_card_type_code_lv1','C','  资管产品'),
    (78,'pjrz','drawer_card_type_code','C01','   其中：资管产品统计编码'),
    (79,'pjrz','drawer_card_type_code','C02','     资管产品登记备案编码'),
    (80,'pjrz','drawer_card_type_code_lv1','L01','  全球法人识别编码（LEI码）'),
    (81,'pjrz','drawer_card_type_code_lv1','Z99','  自定义码'),
    (82,'pjrz','drawer_card_type_code_lv1','NULL','  未填报'),
    (83,'pjrz','合计','合计','按质量分类：'),
    (84,'pjrz','loan_qlty_code','FQ01','  正常'),
    (85,'pjrz','loan_qlty_code','FQ02','  关注'),
    (86,'pjrz','loan_qlty_code','FQ03','  次级'),
    (87,'pjrz','loan_qlty_code','FQ04','  可疑'),
    (88,'pjrz','loan_qlty_code','FQ05','  损失'),
    (89,'pjrz','loan_qlty_code','NULL','  未填报'),
    (90,'pjrz','合计','合计','按状态分类：'),
    (91,'pjrz','loan_sts_code','LS01','  正常'),
    (92,'pjrz','loan_sts_code','LS02','  展期'),
    (93,'pjrz','loan_sts_code','LS03','  逾期'),
    (94,'pjrz','loan_sts_code','LS04','  缩期'),
    (95,'pjrz','loan_sts_code','NULL','  未填报'),
    (96,'ztx','合计','再贴现合计','再贴现合计'),
    (97,'ztx','合计','合计','按币种分类：'),
    (98,'ztx','curr_code','CNY','  人民币'),
    (99,'ztx','curr_code','~CNY','  外币'),
    (100,'ztx','curr_code','NULL','  未填报'),
    (101,'ztx','合计','合计','按再贴现币种分类：'),
    (102,'ztx','rediscount_curr_code','CNY','  人民币'),
    (103,'ztx','rediscount_curr_code','~CNY','  外币'),
    (104,'ztx','rediscount_curr_code','NULL','  未填报'),
    (105,'ztx','合计','合计','按票据种类分类：'),
    (106,'ztx','bill_type_code','01','  银行承兑汇票'),
    (107,'ztx','bill_type_code','02','  商业承兑汇票'),
    (108,'ztx','bill_type_code','03','  财务公司承兑汇票'),
    (109,'ztx','bill_type_code','NULL','  未填报'),
    (110,'ztx','合计','合计','按承兑人证件分类：'),
    (111,'ztx','accept_card_type_code_lv1','A','  单位'),
    (112,'ztx','accept_card_type_code','A01','   其中：统一社会信用代码'),
    (113,'ztx','accept_card_type_code','A02','        组织机构代码'),
    (114,'ztx','accept_card_type_code','A03','        其他'),
    (115,'ztx','accept_card_type_code_lv1','B','  自然人'),
    (116,'ztx','accept_card_type_code','B01','   其中：身份证'),
    (117,'ztx','accept_card_type_code','~B01','        其他证件'),
    (118,'ztx','accept_card_type_code_lv1','C','  资管产品'),
    (119,'ztx','accept_card_type_code','C01','   其中：资管产品统计编码'),
    (120,'ztx','accept_card_type_code','C02','     资管产品登记备案编码'),
    (121,'ztx','accept_card_type_code_lv1','L01','  全球法人识别编码（LEI码）'),
    (122,'ztx','accept_card_type_code_lv1','Z99','  自定义码'),
    (123,'ztx','accept_card_type_code_lv1','NULL','  未填报'),
    (124,'ztx','合计','合计','按出票人证件分类：'),
    (125,'ztx','drawer_card_type_code_lv1','A','  单位'),
    (126,'ztx','drawer_card_type_code','A01','   其中：统一社会信用代码'),
    (127,'ztx','drawer_card_type_code','A02','        组织机构代码'),
    (128,'ztx','drawer_card_type_code','A03','        其他'),
    (129,'ztx','drawer_card_type_code_lv1','B','  自然人'),
    (130,'ztx','drawer_card_type_code','B01','   其中：身份证'),
    (131,'ztx','drawer_card_type_code','~B01','        其他证件'),
    (132,'ztx','drawer_card_type_code_lv1','C','  资管产品'),
    (133,'ztx','drawer_card_type_code','C01','   其中：资管产品统计编码'),
    (134,'ztx','drawer_card_type_code','C02','     资管产品登记备案编码'),
    (135,'ztx','drawer_card_type_code_lv1','L01','  全球法人识别编码（LEI码）'),
    (136,'ztx','drawer_card_type_code_lv1','Z99','  自定义码'),
    (137,'ztx','drawer_card_type_code_lv1','NULL','  未填报'),
    (138,'yhcd','合计','银行承兑汇票合计','银行承兑汇票合计'),
    (139,'yhcd','合计','合计','按币种分类：'),
    (140,'yhcd','curr_code','CNY','  人民币'),
    (141,'yhcd','curr_code','~CNY','  外币'),
    (142,'yhcd','curr_code','NULL','  未填报'),
    (143,'yhcd','合计','合计','按出票人证件分类：'),
    (144,'yhcd','drawer_card_type_code_lv1','A','  单位'),
    (145,'yhcd','drawer_card_type_code','A01','   其中：统一社会信用代码'),
    (146,'yhcd','drawer_card_type_code','A02','        组织机构代码'),
    (147,'yhcd','drawer_card_type_code','A03','        其他'),
    (148,'yhcd','drawer_card_type_code_lv1','B','  自然人'),
    (149,'yhcd','drawer_card_type_code','B01','   其中：身份证'),
    (150,'yhcd','drawer_card_type_code','~B01','        其他证件'),
    (151,'yhcd','drawer_card_type_code_lv1','C','  资管产品'),
    (152,'yhcd','drawer_card_type_code','C01','   其中：资管产品统计编码'),
    (153,'yhcd','drawer_card_type_code','C02','     资管产品登记备案编码'),
    (154,'yhcd','drawer_card_type_code_lv1','L01','  全球法人识别编码（LEI码）'),
    (155,'yhcd','drawer_card_type_code_lv1','Z99','  自定义码'),
    (156,'yhcd','drawer_card_type_code_lv1','NULL','  未填报'),
    (157,'yhcd','合计','合计','按出票人经济成分分类：'),
    (158,'yhcd','drawer_con_eco_elem_code','A01','  国有控股企业'),
    (159,'yhcd','drawer_con_eco_elem_code','A02','  集体控股企业'),
    (160,'yhcd','drawer_con_eco_elem_code','B01','  私人控股企业'),
    (161,'yhcd','drawer_con_eco_elem_code','B02','  港澳台商控股企业'),
    (162,'yhcd','drawer_con_eco_elem_code','B03','  外商控股企业'),
    (163,'yhcd','drawer_con_eco_elem_code','NULL','  未填报'),
    (164,'yhcd','合计','合计','按出票人规模分类：'),
    (165,'yhcd','drawer_ent_scale_code','CS01','  大型'),
    (166,'yhcd','drawer_ent_scale_code','CS02','  中型'),
    (167,'yhcd','drawer_ent_scale_code','CS03','  小型'),
    (168,'yhcd','drawer_ent_scale_code','CS04','  微型'),
    (169,'yhcd','drawer_ent_scale_code','CS05','  其他'),
    (170,'yhcd','drawer_ent_scale_code','NULL','  未填报'),
    (171,'yhcd','合计','合计','按收款人证件分类：'),
    (172,'yhcd','rece_card_type_code_lv1','A','  单位'),
    (173,'yhcd','rece_card_type_code','A01','   其中：统一社会信用代码'),
    (174,'yhcd','rece_card_type_code','A02','        组织机构代码'),
    (175,'yhcd','rece_card_type_code','A03','        其他'),
    (176,'yhcd','rece_card_type_code_lv1','B','  自然人'),
    (177,'yhcd','rece_card_type_code','B01','   其中：身份证'),
    (178,'yhcd','rece_card_type_code','~B01','        其他证件'),
    (179,'yhcd','rece_card_type_code_lv1','C','  资管产品'),
    (180,'yhcd','rece_card_type_code','C01','   其中：资管产品统计编码'),
    (181,'yhcd','rece_card_type_code','C02','     资管产品登记备案编码'),
    (182,'yhcd','rece_card_type_code_lv1','L01','  全球法人识别编码（LEI码）'),
    (183,'yhcd','rece_card_type_code_lv1','Z99','  自定义码'),
    (184,'yhcd','rece_card_type_code_lv1','NULL','  未填报'),
    (185,'yhcd','合计','合计','按担保方式分类：'),
    (186,'yhcd','guar_mode_code','A','  质押贷款'),
    (187,'yhcd','guar_mode_code','B','  抵押贷款'),
    (188,'yhcd','guar_mode_code','C','  保证贷款'),
    (189,'yhcd','guar_mode_code','D','  信用/免担保贷款'),
    (190,'yhcd','guar_mode_code','E','  组合贷款'),
    (191,'yhcd','guar_mode_code','Z','  其他'),
    (192,'yhcd','guar_mode_code','NULL','  未填报')
    t(group_type_order,sourc_bw,group_type_code,group_type_value,group_type_value_rp)
)

,
pbc_info AS (
    SELECT   fin_org_code
            ,fin_org_name
            ,fin_org_pbc_code
            ,fin_org_pbc_name
            ,fin_org_pbc_code_lv1
            ,fin_org_pbc_name_lv1
            ,fin_org_pbc_code_lv2
            ,fin_org_pbc_name_lv2
            ,fin_org_pbc_code_lv3
            ,fin_org_pbc_name_lv3
    FROM    odps_prd_olver.ver_fin_org_pbc_info
)
,
pbc_type AS (
    SELECT DISTINCT
            fin_org_pbc_code_lv1 AS fin_org_pbc_code,
            fin_org_pbc_name_lv1 AS fin_org_pbc_name
    FROM    odps_prd_olver.ver_fin_org_pbc_info
    WHERE   fin_org_pbc_code_lv1 IS NOT NULL
      AND   fin_org_pbc_code_lv2 IS NULL
      AND   fin_org_pbc_code_lv3 IS NULL

    UNION ALL

    SELECT DISTINCT
            fin_org_pbc_code_lv2 AS fin_org_pbc_code,
            fin_org_pbc_name_lv2 AS fin_org_pbc_name
    FROM    odps_prd_olver.ver_fin_org_pbc_info
    WHERE   fin_org_pbc_code_lv1 IS NOT NULL
      AND   fin_org_pbc_code_lv2 IS NOT NULL
      AND   fin_org_pbc_code_lv3 IS NULL

    UNION ALL

    SELECT DISTINCT
            fin_org_pbc_code_lv3 AS fin_org_pbc_code,
            fin_org_pbc_name_lv3 AS fin_org_pbc_name
    FROM    odps_prd_olver.ver_fin_org_pbc_info
    WHERE   fin_org_pbc_code_lv1 IS NOT NULL
      AND   fin_org_pbc_code_lv2 IS NOT NULL
      AND   fin_org_pbc_code_lv3 IS NOT NULL
)
,
rp_type AS (
    SELECT   a.fin_org_pbc_code
            ,a.fin_org_pbc_name
            ,b.group_type_order
            ,b.sourc_bw
            ,b.group_type_code
            ,b.group_type_value
            ,b.group_type_value_rp
    FROM     pbc_type a
    CROSS JOIN pjrz_type b
)
,
card_type_code_lv1 AS (
    SELECT  DISTINCT
            card_type_code
            ,IF(
                card_type_code IN ('L01','Z99')
                ,card_type_code
                ,SUBSTR(card_type_code,1,1)
            ) AS card_type_value_lv1
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_card_type_c0080
)
,
card_type_code AS (
    SELECT  DISTINCT
            card_type_code
            ,IF(
                SUBSTR(card_type_code,1,1) = 'B' AND card_type_code <> 'B01'
                ,'~B01'
                ,card_type_code
            ) AS card_type_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_card_type_c0080
)
,
ent_eco_sector_code_lv1 AS (
    SELECT  DISTINCT
            eco_sector_code
            ,SUBSTR(eco_sector_code,1,1) AS ent_eco_sector_value_lv1
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_eco_sector_c0011
)
,
ent_eco_elem_code AS (
    SELECT  DISTINCT
            eco_elem_code
            ,SUBSTR(eco_elem_code,1,3) AS ent_eco_elem_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_eco_elem_c0014
)
,
ent_scale_code AS (
    SELECT  DISTINCT
            ent_scale_code
            ,ent_scale_code AS ent_scale_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_ent_scale_c0015
)
,
curr_code AS (
    SELECT  DISTINCT
            curr_code
            ,CASE
                WHEN curr_code IS NULL THEN NULL
                WHEN curr_code <> 'CNY' THEN '~CNY'
                ELSE 'CNY'
             END AS curr_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_curr_c0004
)
,
loan_guar_mode_code_lv1 AS (
    SELECT  DISTINCT
            loan_guar_mode_code
            ,SUBSTR(loan_guar_mode_code,1,1) AS loan_guar_mode_value_lv1
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_loan_guar_mode_c0019
)
,
loan_qlty_code AS (
    SELECT  DISTINCT
            loan_qlty_code
            ,loan_qlty_code AS loan_qlty_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_loan_qlty_c0021
)
,
loan_sts_code AS (
    SELECT  DISTINCT
            loan_sts1_code
            ,loan_sts1_code AS loan_sts_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_loan_sts1_c0022
)
,
discount_type_code AS (
    SELECT  DISTINCT
            discount_type_code
            ,discount_type_code AS discount_type_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_discount_type_c0022
)
,
bill_type_code AS (
    SELECT  DISTINCT
            bill_type_code
            ,bill_type_code AS bill_type_value
            ,b_date
            ,e_date
    FROM    odps_prd_dim.dim_bill_type_c0022
)

,
pjrz_data AS (
    SELECT
        fin_org_code,
        CASE
            WHEN dt = '${p_month_yyyymm}' THEN 'bq'
            ELSE 'sq'
        END AS data_type,
        bill_amt_rmb,
        int_rate,
        dt,
        TO_DATE(a.dt,'yyyymm') AS dt_date,
        curr_code,
        discount_curr_code,
        discount_type_code,
        bill_type_code,
        discount_card_type_code,
        discount_eco_sector_code,
        discount_ent_eco_elem_code,
        discount_ent_scale_code,
        accept_card_type_code,
        drawer_card_type_code,
        loan_qlty_code,
        loan_sts_code
    FROM odps_prd_ods.ods_js_205_clpjrz a
    WHERE dt IN (
        '${p_month_yyyymm}',
        IF(SUBSTR('${p_month_yyyymm}',5,2) = '01', '${p_month_yyyymm}' - 89, '${p_month_yyyymm}' - 1)
    )

    UNION ALL

    SELECT
        fin_org_code,
        CASE
            WHEN trans_type_code IN ('A01','A02','A09') THEN 'ff'
            WHEN trans_type_code IN ('B01','B02','B03','B04','B09') THEN 'jq'
        END AS data_type,
        bill_amt_rmb,
        int_rate,
        dt,
        TO_DATE(a.dt,'yyyymm') AS dt_date,
        curr_code,
        discount_curr_code,
        discount_type_code,
        bill_type_code,
        discount_card_type_code,
        discount_eco_sector_code,
        discount_ent_eco_elem_code,
        discount_ent_scale_code,
        accept_card_type_code,
        drawer_card_type_code,
        loan_qlty_code,
        loan_sts_code
    FROM odps_prd_ods.ods_js_205_pjrzfs a
    WHERE dt = '${p_month_yyyymm}'
)
,
pjrz_val AS (
    SELECT  /*+ MAPJOIN(c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15) */
            a.data_type
            ,a.fin_org_code
            ,a.bill_amt_rmb
            ,a.int_rate
            ,COALESCE(c1.curr_value,'NULL') AS curr_code
            ,COALESCE(c2.curr_value,'NULL') AS discount_curr_code
            ,COALESCE(c3.discount_type_value,'NULL') AS discount_type_code
            ,COALESCE(c4.bill_type_value,'NULL') AS bill_type_code
            ,COALESCE(c5.card_type_value_lv1,'NULL') AS discount_card_type_code_lv1
            ,COALESCE(c6.card_type_value,'NULL') AS discount_card_type_code
            ,COALESCE(c7.ent_eco_sector_value_lv1,'NULL') AS discount_eco_sector_code
            ,COALESCE(c8.ent_eco_elem_value,'NULL') AS discount_ent_eco_elem_code
            ,COALESCE(c9.ent_scale_value,'NULL') AS discount_ent_scale_code
            ,COALESCE(c10.card_type_value_lv1,'NULL') AS accept_card_type_code_lv1
            ,COALESCE(c11.card_type_value,'NULL') AS accept_card_type_code
            ,COALESCE(c12.card_type_value_lv1,'NULL') AS drawer_card_type_code_lv1
            ,COALESCE(c13.card_type_value,'NULL') AS drawer_card_type_code
            ,COALESCE(c14.loan_qlty_value,'NULL') AS loan_qlty_code
            ,COALESCE(c15.loan_sts_value,'NULL') AS loan_sts_code
            ,a.dt
    FROM    pjrz_data a
    LEFT JOIN curr_code c1
           ON a.curr_code = c1.curr_code
          AND a.dt_date BETWEEN c1.b_date AND c1.e_date
    LEFT JOIN curr_code c2
           ON a.discount_curr_code = c2.curr_code
          AND a.dt_date BETWEEN c2.b_date AND c2.e_date
    LEFT JOIN discount_type_code c3
           ON a.discount_type_code = c3.discount_type_code
          AND a.dt_date BETWEEN c3.b_date AND c3.e_date
    LEFT JOIN bill_type_code c4
           ON a.bill_type_code = c4.bill_type_code
          AND a.dt_date BETWEEN c4.b_date AND c4.e_date
    LEFT JOIN card_type_code_lv1 c5
           ON a.discount_card_type_code = c5.card_type_code
          AND a.dt_date BETWEEN c5.b_date AND c5.e_date
    LEFT JOIN card_type_code c6
           ON a.discount_card_type_code = c6.card_type_code
          AND a.dt_date BETWEEN c6.b_date AND c6.e_date
    LEFT JOIN ent_eco_sector_code_lv1 c7
           ON a.discount_eco_sector_code = c7.eco_sector_code
          AND a.dt_date BETWEEN c7.b_date AND c7.e_date
    LEFT JOIN ent_eco_elem_code c8
           ON a.discount_ent_eco_elem_code = c8.eco_elem_code
          AND a.dt_date BETWEEN c8.b_date AND c8.e_date
    LEFT JOIN ent_scale_code c9
           ON a.discount_ent_scale_code = c9.ent_scale_code
          AND a.dt_date BETWEEN c9.b_date AND c9.e_date
    LEFT JOIN card_type_code_lv1 c10
           ON a.accept_card_type_code = c10.card_type_code
          AND a.dt_date BETWEEN c10.b_date AND c10.e_date
    LEFT JOIN card_type_code c11
           ON a.accept_card_type_code = c11.card_type_code
          AND a.dt_date BETWEEN c11.b_date AND c11.e_date
    LEFT JOIN card_type_code_lv1 c12
           ON a.drawer_card_type_code = c12.card_type_code
          AND a.dt_date BETWEEN c12.b_date AND c12.e_date
    LEFT JOIN card_type_code c13
           ON a.drawer_card_type_code = c13.card_type_code
          AND a.dt_date BETWEEN c13.b_date AND c13.e_date
    LEFT JOIN loan_qlty_code c14
           ON a.loan_qlty_code = c14.loan_qlty_code
          AND a.dt_date BETWEEN c14.b_date AND c14.e_date
    LEFT JOIN loan_sts_code c15
           ON a.loan_sts_code = c15.loan_sts1_code
          AND a.dt_date BETWEEN c15.b_date AND c15.e_date
    DISTRIBUTE BY RAND()
)
,
pjrz_preagg AS (
    SELECT
        fin_org_code,
        data_type,
        curr_code,
        discount_curr_code,
        discount_type_code,
        bill_type_code,
        discount_card_type_code_lv1,
        discount_card_type_code,
        discount_eco_sector_code,
        discount_ent_eco_elem_code,
        discount_ent_scale_code,
        accept_card_type_code_lv1,
        accept_card_type_code,
        drawer_card_type_code_lv1,
        drawer_card_type_code,
        loan_qlty_code,
        loan_sts_code,
        SUM(bill_amt_rmb) AS bill_amt_rmb,
        SUM(IF(discount_type_code = '01' AND int_rate IS NOT NULL, bill_amt_rmb * int_rate, 0)) AS amt_rate,
        SUM(IF(discount_type_code = '01' AND int_rate IS NOT NULL, bill_amt_rmb, 0)) AS rate_bill_amt_rmb,
        dt
    FROM pjrz_val
    GROUP BY
        fin_org_code,
        data_type,
        curr_code,
        discount_curr_code,
        discount_type_code,
        bill_type_code,
        discount_card_type_code_lv1,
        discount_card_type_code,
        discount_eco_sector_code,
        discount_ent_eco_elem_code,
        discount_ent_scale_code,
        accept_card_type_code_lv1,
        accept_card_type_code,
        drawer_card_type_code_lv1,
        drawer_card_type_code,
        loan_qlty_code,
        loan_sts_code,
        dt
)
,
pjrz_exploded AS (
    SELECT
        data_type,
        fin_org_code,
        k AS group_type_code,
        v AS group_type_value,
        bill_amt_rmb,
        amt_rate,
        rate_bill_amt_rmb,
        dt
    FROM pjrz_preagg
    LATERAL VIEW EXPLODE(MAP(
        'curr_code',curr_code,
        'discount_curr_code',discount_curr_code,
        'discount_type_code',discount_type_code,
        'bill_type_code',bill_type_code,
        'discount_card_type_code_lv1',discount_card_type_code_lv1,
        'discount_card_type_code',discount_card_type_code,
        'discount_eco_sector_code',discount_eco_sector_code,
        'discount_ent_eco_elem_code',discount_ent_eco_elem_code,
        'discount_ent_scale_code',discount_ent_scale_code,
        'accept_card_type_code_lv1',accept_card_type_code_lv1,
        'accept_card_type_code',accept_card_type_code,
        'drawer_card_type_code_lv1',drawer_card_type_code_lv1,
        'drawer_card_type_code',drawer_card_type_code,
        'loan_qlty_code',loan_qlty_code,
        'loan_sts_code',loan_sts_code,
        '合计','票据融资合计'
    )) t AS k, v
)
,
pjrz_fin_org_cal AS (
    SELECT
        fin_org_code,
        group_type_code,
        group_type_value,
        data_type,
        SUM(bill_amt_rmb) AS bill_amt_rmb,
        SUM(amt_rate) AS amt_rate,
        SUM(rate_bill_amt_rmb) AS rate_bill_amt_rmb,
        dt
    FROM pjrz_exploded
    GROUP BY
        fin_org_code,
        group_type_code,
        group_type_value,
        data_type,
        dt
)

,
ztx_data AS (
    SELECT
        fin_org_code,
        CASE
            WHEN dt = '${p_month_yyyymm}' THEN 'bq'
            ELSE 'sq'
        END AS data_type,
        bill_amt_rmb,
        int_rate,
        dt,
        TO_DATE(a.dt,'yyyymm') AS dt_date,
        curr_code,
        rediscount_curr_code,
        bill_type_code,
        accept_card_type_code,
        drawer_card_type_code
    FROM odps_prd_ods.ods_js_205_clztx a
    WHERE dt IN (
        '${p_month_yyyymm}',
        IF(SUBSTR('${p_month_yyyymm}',5,2) = '01', '${p_month_yyyymm}' - 89, '${p_month_yyyymm}' - 1)
    )

    UNION ALL

    SELECT
        fin_org_code,
        CASE
            WHEN rediscount_trans_flg_code = '1' THEN 'ff'
            WHEN rediscount_trans_flg_code = '0' THEN 'jq'
        END AS data_type,
        bill_amt_rmb,
        int_rate,
        dt,
        TO_DATE(a.dt,'yyyymm') AS dt_date,
        curr_code,
        rediscount_curr_code,
        bill_type_code,
        accept_card_type_code,
        drawer_card_type_code
    FROM odps_prd_ods.ods_js_205_ztxfs a
    WHERE dt = '${p_month_yyyymm}'
)
,
ztx_val AS (
    SELECT  /*+ MAPJOIN(c1, c2, c4, c10, c11, c12, c13) */
            a.data_type
            ,a.fin_org_code
            ,a.bill_amt_rmb
            ,a.int_rate
            ,COALESCE(c1.curr_value,'NULL') AS curr_code
            ,COALESCE(c2.curr_value,'NULL') AS rediscount_curr_code
            ,COALESCE(c4.bill_type_value,'NULL') AS bill_type_code
            ,COALESCE(c10.card_type_value_lv1,'NULL') AS accept_card_type_code_lv1
            ,COALESCE(c11.card_type_value,'NULL') AS accept_card_type_code
            ,COALESCE(c12.card_type_value_lv1,'NULL') AS drawer_card_type_code_lv1
            ,COALESCE(c13.card_type_value,'NULL') AS drawer_card_type_code
            ,a.dt
    FROM    ztx_data a
    LEFT JOIN curr_code c1
           ON a.curr_code = c1.curr_code
          AND a.dt_date BETWEEN c1.b_date AND c1.e_date
    LEFT JOIN curr_code c2
           ON a.rediscount_curr_code = c2.curr_code
          AND a.dt_date BETWEEN c2.b_date AND c2.e_date
    LEFT JOIN bill_type_code c4
           ON a.bill_type_code = c4.bill_type_code
          AND a.dt_date BETWEEN c4.b_date AND c4.e_date
    LEFT JOIN card_type_code_lv1 c10
           ON a.accept_card_type_code = c10.card_type_code
          AND a.dt_date BETWEEN c10.b_date AND c10.e_date
    LEFT JOIN card_type_code c11
           ON a.accept_card_type_code = c11.card_type_code
          AND a.dt_date BETWEEN c11.b_date AND c11.e_date
    LEFT JOIN card_type_code_lv1 c12
           ON a.drawer_card_type_code = c12.card_type_code
          AND a.dt_date BETWEEN c12.b_date AND c12.e_date
    LEFT JOIN card_type_code c13
           ON a.drawer_card_type_code = c13.card_type_code
          AND a.dt_date BETWEEN c13.b_date AND c13.e_date
    DISTRIBUTE BY RAND()
)
,
ztx_preagg AS (
    SELECT
        fin_org_code,
        data_type,
        curr_code,
        rediscount_curr_code,
        bill_type_code,
        accept_card_type_code_lv1,
        accept_card_type_code,
        drawer_card_type_code_lv1,
        drawer_card_type_code,
        SUM(bill_amt_rmb) AS bill_amt_rmb,
        SUM(IF(discount_type_code = '01' AND int_rate IS NOT NULL, bill_amt_rmb * int_rate, 0)) AS amt_rate,
        SUM(IF(discount_type_code = '01' AND int_rate IS NOT NULL, bill_amt_rmb, 0)) AS rate_bill_amt_rmb,
        dt
    FROM ztx_val
    GROUP BY
        fin_org_code,
        data_type,
        curr_code,
        rediscount_curr_code,
        bill_type_code,
        accept_card_type_code_lv1,
        accept_card_type_code,
        drawer_card_type_code_lv1,
        drawer_card_type_code,
        dt
)
,
ztx_exploded AS (
    SELECT
        data_type,
        fin_org_code,
        k AS group_type_code,
        v AS group_type_value,
        bill_amt_rmb,
        amt_rate,
        dt
    FROM ztx_preagg
    LATERAL VIEW EXPLODE(MAP(
        'curr_code',curr_code,
        'rediscount_curr_code',rediscount_curr_code,
        'bill_type_code',bill_type_code,
        'accept_card_type_code_lv1',accept_card_type_code_lv1,
        'accept_card_type_code',accept_card_type_code,
        'drawer_card_type_code_lv1',drawer_card_type_code_lv1,
        'drawer_card_type_code',drawer_card_type_code,
        '合计','再贴现合计'
    )) t AS k, v
)
,
ztx_fin_org_cal AS (
    SELECT
        fin_org_code,
        group_type_code,
        group_type_value,
        data_type,
        SUM(bill_amt_rmb) AS bill_amt_rmb,
        SUM(amt_rate) AS amt_rate,
        dt
    FROM ztx_exploded
    GROUP BY
        fin_org_code,
        group_type_code,
        group_type_value,
        data_type,
        dt
)

,
yhcd_data AS (
    SELECT
        fin_org_code,
        CASE
            WHEN dt = '${p_month_yyyymm}' THEN 'bq'
            ELSE 'sq'
        END AS data_type,
        bill_amt_rmb,
        dt,
        TO_DATE(a.dt,'yyyymm') AS dt_date,
        curr_code,
        drawer_card_type_code,
        drawer_con_eco_elem_code,
        drawer_ent_scale_code,
        rece_card_type_code,
        guar_mode_code
    FROM odps_prd_ods.ods_js_205_clyhcd a
    WHERE dt IN (
        '${p_month_yyyymm}',
        IF(SUBSTR('${p_month_yyyymm}',5,2) = '01', '${p_month_yyyymm}' - 89, '${p_month_yyyymm}' - 1)
    )

    UNION ALL

    SELECT
        fin_org_code,
        CASE
            WHEN trans_type_code = '01' THEN 'ff'
            WHEN trans_type_code = '02' THEN 'jq'
        END AS data_type,
        bill_amt_rmb,
        dt,
        TO_DATE(a.dt,'yyyymm') AS dt_date,
        curr_code,
        drawer_card_type_code,
        drawer_con_eco_elem_code,
        drawer_ent_scale_code,
        rece_card_type_code,
        guar_mode_code
    FROM odps_prd_ods.ods_js_205_yhcdfs a
    WHERE dt = '${p_month_yyyymm}'
)
,
yhcd_val AS (
    SELECT  /*+ MAPJOIN(c1, c5, c6, c8, c9, c10, c11, c16) */
            a.data_type
            ,a.fin_org_code
            ,a.bill_amt_rmb
            ,COALESCE(c1.curr_value,'NULL') AS curr_code
            ,COALESCE(c5.card_type_value_lv1,'NULL') AS drawer_card_type_code_lv1
            ,COALESCE(c6.card_type_value,'NULL') AS drawer_card_type_code
            ,COALESCE(c8.ent_eco_elem_value,'NULL') AS drawer_con_eco_elem_code
            ,COALESCE(c9.ent_scale_value,'NULL') AS drawer_ent_scale_code
            ,COALESCE(c10.card_type_value_lv1,'NULL') AS rece_card_type_code_lv1
            ,COALESCE(c11.card_type_value,'NULL') AS rece_card_type_code
            ,COALESCE(c16.loan_guar_mode_value_lv1,'NULL') AS guar_mode_code
            ,a.dt
    FROM    yhcd_data a
    LEFT JOIN curr_code c1
           ON a.curr_code = c1.curr_code
          AND a.dt_date BETWEEN c1.b_date AND c1.e_date
    LEFT JOIN card_type_code_lv1 c5
           ON a.drawer_card_type_code = c5.card_type_code
          AND a.dt_date BETWEEN c5.b_date AND c5.e_date
    LEFT JOIN card_type_code c6
           ON a.drawer_card_type_code = c6.card_type_code
          AND a.dt_date BETWEEN c6.b_date AND c6.e_date
    LEFT JOIN ent_eco_elem_code c8
           ON a.drawer_con_eco_elem_code = c8.eco_elem_code
          AND a.dt_date BETWEEN c8.b_date AND c8.e_date
    LEFT JOIN ent_scale_code c9
           ON a.drawer_ent_scale_code = c9.ent_scale_code
          AND a.dt_date BETWEEN c9.b_date AND c9.e_date
    LEFT JOIN card_type_code_lv1 c10
           ON a.rece_card_type_code = c10.card_type_code
          AND a.dt_date BETWEEN c10.b_date AND c10.e_date
    LEFT JOIN card_type_code c11
           ON a.rece_card_type_code = c11.card_type_code
          AND a.dt_date BETWEEN c11.b_date AND c11.e_date
    LEFT JOIN loan_guar_mode_code_lv1 c16
           ON a.guar_mode_code = c16.loan_guar_mode_code
          AND a.dt_date BETWEEN c16.b_date AND c16.e_date
    DISTRIBUTE BY RAND()
)
,
yhcd_preagg AS (
    SELECT
        fin_org_code,
        data_type,
        curr_code,
        drawer_card_type_code_lv1,
        drawer_card_type_code,
        drawer_con_eco_elem_code,
        drawer_ent_scale_code,
        rece_card_type_code_lv1,
        rece_card_type_code,
        guar_mode_code,
        SUM(bill_amt_rmb) AS bill_amt_rmb,
        dt
    FROM yhcd_val
    GROUP BY
        fin_org_code,
        data_type,
        curr_code,
        drawer_card_type_code_lv1,
        drawer_card_type_code,
        drawer_con_eco_elem_code,
        drawer_ent_scale_code,
        rece_card_type_code_lv1,
        rece_card_type_code,
        guar_mode_code,
        dt
)
,
yhcd_exploded AS (
    SELECT
        data_type,
        fin_org_code,
        k AS group_type_code,
        v AS group_type_value,
        bill_amt_rmb,
        dt
    FROM yhcd_preagg
    LATERAL VIEW EXPLODE(MAP(
        'curr_code',curr_code,
        'drawer_card_type_code_lv1',drawer_card_type_code_lv1,
        'drawer_card_type_code',drawer_card_type_code,
        'drawer_con_eco_elem_code',drawer_con_eco_elem_code,
        'drawer_ent_scale_code',drawer_ent_scale_code,
        'rece_card_type_code_lv1',rece_card_type_code_lv1,
        'rece_card_type_code',rece_card_type_code,
        'guar_mode_code',guar_mode_code,
        '合计','银行承兑汇票合计'
    )) t AS k, v
)
,
yhcd_fin_org_cal AS (
    SELECT
        fin_org_code,
        group_type_code,
        group_type_value,
        data_type,
        SUM(bill_amt_rmb) AS bill_amt_rmb,
        dt
    FROM yhcd_exploded
    GROUP BY
        fin_org_code,
        group_type_code,
        group_type_value,
        data_type,
        dt
)

,
pjrz_cal AS (
    SELECT /*+ MAPJOIN(a) */
        CASE
            WHEN GROUPING(b.fin_org_pbc_code_lv3) = 0 THEN b.fin_org_pbc_code_lv3
            WHEN GROUPING(b.fin_org_pbc_code_lv2) = 0 THEN b.fin_org_pbc_code_lv2
            WHEN GROUPING(b.fin_org_pbc_code_lv1) = 0 THEN b.fin_org_pbc_code_lv1
        END AS fin_org_pbc_code,
        a.group_type_code,
        a.group_type_value,
        SUM(IF(a.data_type = 'bq',a.bill_amt_rmb,0)) AS bill_amt_rmb_bq,
        SUM(IF(a.data_type = 'sq',a.bill_amt_rmb,0)) AS bill_amt_rmb_sq,
        SUM(IF(a.data_type = 'ff',a.bill_amt_rmb,0)) AS buy_amt_rmb_bq,
        SUM(IF(a.data_type = 'jq',a.bill_amt_rmb,0)) AS sell_amt_rmb_bq,
        CASE WHEN SUM(IF(a.data_type = 'bq',a.rate_bill_amt_rmb,0)) = 0 THEN NULL
             ELSE SUM(IF(a.data_type = 'bq',a.amt_rate,0)) / SUM(IF(a.data_type = 'bq',a.rate_bill_amt_rmb,0))
        END AS int_rate_bq,
        CASE WHEN SUM(IF(a.data_type = 'sq',a.rate_bill_amt_rmb,0)) = 0 THEN NULL
             ELSE SUM(IF(a.data_type = 'sq',a.amt_rate,0)) / SUM(IF(a.data_type = 'sq',a.rate_bill_amt_rmb,0))
        END AS int_rate_sq,
        CASE WHEN SUM(IF(a.data_type = 'ff',a.rate_bill_amt_rmb,0)) = 0 THEN NULL
             ELSE SUM(IF(a.data_type = 'ff',a.amt_rate,0)) / SUM(IF(a.data_type = 'ff',a.rate_bill_amt_rmb,0))
        END AS buy_grant_int_rate,
        a.dt
    FROM    pbc_info b
    LEFT JOIN    pjrz_fin_org_cal a
      ON    a.fin_org_code = b.fin_org_code
    GROUP BY
        a.group_type_code,
        a.group_type_value,
        a.dt,
        GROUPING SETS(
            (b.fin_org_pbc_code_lv1),
            (b.fin_org_pbc_code_lv1,b.fin_org_pbc_code_lv2),
            (b.fin_org_pbc_code_lv1,b.fin_org_pbc_code_lv2,b.fin_org_pbc_code_lv3)
        )
)
,
ztx_cal AS (
    SELECT /*+ MAPJOIN(a) */
        CASE
            WHEN GROUPING(b.fin_org_pbc_code_lv3) = 0 THEN b.fin_org_pbc_code_lv3
            WHEN GROUPING(b.fin_org_pbc_code_lv2) = 0 THEN b.fin_org_pbc_code_lv2
            WHEN GROUPING(b.fin_org_pbc_code_lv1) = 0 THEN b.fin_org_pbc_code_lv1
        END AS fin_org_pbc_code,
        a.group_type_code,
        a.group_type_value,
        SUM(IF(a.data_type = 'bq',a.bill_amt_rmb,0)) AS bill_amt_rmb_bq,
        SUM(IF(a.data_type = 'sq',a.bill_amt_rmb,0)) AS bill_amt_rmb_sq,
        SUM(IF(a.data_type = 'ff',a.bill_amt_rmb,0)) AS buy_amt_rmb_bq,
        SUM(IF(a.data_type = 'jq',a.bill_amt_rmb,0)) AS sell_amt_rmb_bq,
        CASE WHEN SUM(IF(a.data_type = 'bq',a.rate_bill_amt_rmb,0)) = 0 THEN NULL
             ELSE SUM(IF(a.data_type = 'bq',a.amt_rate,0)) / SUM(IF(a.data_type = 'bq',a.rate_bill_amt_rmb,0))
        END AS int_rate_bq,
        CASE WHEN SUM(IF(a.data_type = 'sq',a.rate_bill_amt_rmb,0)) = 0 THEN NULL
             ELSE SUM(IF(a.data_type = 'sq',a.amt_rate,0)) / SUM(IF(a.data_type = 'sq',a.rate_bill_amt_rmb,0))
        END AS int_rate_sq,
        CASE WHEN SUM(IF(a.data_type = 'ff',a.rate_bill_amt_rmb,0)) = 0 THEN NULL
             ELSE SUM(IF(a.data_type = 'ff',a.amt_rate,0)) / SUM(IF(a.data_type = 'ff',a.rate_bill_amt_rmb,0))
        END AS buy_grant_int_rate,
        a.dt
    FROM    pbc_info b
    LEFT JOIN    ztx_fin_org_cal a
      ON    a.fin_org_code = b.fin_org_code
    GROUP BY
        a.group_type_code,
        a.group_type_value,
        a.dt,
        GROUPING SETS(
            (b.fin_org_pbc_code_lv1),
            (b.fin_org_pbc_code_lv1,b.fin_org_pbc_code_lv2),
            (b.fin_org_pbc_code_lv1,b.fin_org_pbc_code_lv2,b.fin_org_pbc_code_lv3)
        )
)
,
yhcd_cal AS (
    SELECT /*+ MAPJOIN(a) */
        CASE
            WHEN GROUPING(b.fin_org_pbc_code_lv3) = 0 THEN b.fin_org_pbc_code_lv3
            WHEN GROUPING(b.fin_org_pbc_code_lv2) = 0 THEN b.fin_org_pbc_code_lv2
            WHEN GROUPING(b.fin_org_pbc_code_lv1) = 0 THEN b.fin_org_pbc_code_lv1
        END AS fin_org_pbc_code,
        a.group_type_code,
        a.group_type_value,
        SUM(IF(a.data_type = 'bq',a.bill_amt_rmb,0)) AS bill_amt_rmb_bq,
        SUM(IF(a.data_type = 'sq',a.bill_amt_rmb,0)) AS bill_amt_rmb_sq,
        SUM(IF(a.data_type = 'ff',a.bill_amt_rmb,0)) AS buy_amt_rmb_bq,
        SUM(IF(a.data_type = 'jq',a.bill_amt_rmb,0)) AS sell_amt_rmb_bq,
        a.dt
    FROM    pbc_info b
    LEFT JOIN    yhcd_fin_org_cal a
      ON    a.fin_org_code = b.fin_org_code
    GROUP BY
        a.group_type_code,
        a.group_type_value,
        a.dt,
        GROUPING SETS(
            (b.fin_org_pbc_code_lv1),
            (b.fin_org_pbc_code_lv1,b.fin_org_pbc_code_lv2),
            (b.fin_org_pbc_code_lv1,b.fin_org_pbc_code_lv2,b.fin_org_pbc_code_lv3)
        )
)
,
pj_cal AS (
    SELECT
        fin_org_pbc_code,
        'pjrz' AS sourc_bw,
        group_type_code,
        group_type_value,
        bill_amt_rmb_bq,
        bill_amt_rmb_sq,
        buy_amt_rmb_bq,
        sell_amt_rmb_bq,
        int_rate_bq,
        int_rate_sq,
        buy_grant_int_rate,
        dt
    FROM pjrz_cal

    UNION ALL

    SELECT
        fin_org_pbc_code,
        'ztx' AS sourc_bw,
        group_type_code,
        group_type_value,
        bill_amt_rmb_bq,
        bill_amt_rmb_sq,
        buy_amt_rmb_bq,
        sell_amt_rmb_bq,
        int_rate_bq,
        int_rate_sq,
        buy_grant_int_rate,
        dt
    FROM ztx_cal

    UNION ALL

    SELECT
        fin_org_pbc_code,
        'yhcd' AS sourc_bw,
        group_type_code,
        group_type_value,
        bill_amt_rmb_bq,
        bill_amt_rmb_sq,
        buy_amt_rmb_bq,
        sell_amt_rmb_bq,
        NULL,
        NULL,
        NULL,
        dt
    FROM yhcd_cal
)
,
pj_res AS (
    SELECT  /*+ MAPJOIN(a) */
            a.fin_org_pbc_code,
            a.fin_org_pbc_name,
            a.group_type_order,
            a.group_type_code AS group_type_name,
            a.group_type_value_rp AS group_type_value,

            COALESCE(b.bill_amt_rmb_bq,0) / 1e4 AS bill_amt_rmb_bq,
            COALESCE(b.bill_amt_rmb_sq,0) / 1e4 AS bill_amt_rmb_sq,
            COALESCE(b.buy_amt_rmb_bq,0) / 1e4 AS buy_amt_rmb_bq,
            COALESCE(b.sell_amt_rmb_bq,0) / 1e4 AS sell_amt_rmb_bq,
            CASE
                WHEN COALESCE(b.bill_amt_rmb_sq,0) = 0 THEN NULL
                ELSE (COALESCE(b.bill_amt_rmb_bq,0) / b.bill_amt_rmb_sq - 1) * 100
            END AS bill_amt_rmb_mom,
            (COALESCE(b.bill_amt_rmb_bq,0) - COALESCE(b.bill_amt_rmb_sq,0) - COALESCE(b.buy_amt_rmb_bq,0) + COALESCE(b.sell_amt_rmb_bq,0)) / 1e4 AS bill_amt_rmb_chk,
            b.int_rate_bq AS int_rate_bq,
            b.int_rate_sq AS int_rate_sq,
            b.buy_grant_int_rate AS buy_grant_int_rate,
            LAST_DAY(TO_DATE('${p_month_yyyymm}','yyyymm')) AS data_date,
            '${p_month_yyyymm}' AS dt
    FROM rp_type a
    LEFT JOIN pj_cal b
           ON a.fin_org_pbc_code = b.fin_org_pbc_code
          AND a.sourc_bw = b.sourc_bw
          AND a.group_type_code = b.group_type_code
          AND a.group_type_value = b.group_type_value
)

INSERT OVERWRITE TABLE odps_prd_olver.ver_hc_pj_situ_pbc_admin PARTITION (dt='${p_month_yyyymm}', batch_num)
SELECT
    fin_org_pbc_code,
    fin_org_pbc_name,
    group_type_order,
    group_type_name,
    group_type_value,
    bill_amt_rmb_bq,
    bill_amt_rmb_sq,
    buy_amt_rmb_bq,
    sell_amt_rmb_bq,
    bill_amt_rmb_mom,
    bill_amt_rmb_chk,
    int_rate_bq,
    int_rate_sq,
    buy_grant_int_rate,
    data_date,
    (SELECT MAX(batch_num) FROM odps_prd_olver.ver_submit_org_md WHERE sourc_bw = 'pj' AND dt = '${p_month_yyyymm}')
FROM pj_res
;

INSERT OVERWRITE TABLE odps_prd_olver.ver_hc_tszb PARTITION (dt='${p_month_yyyymm}', hc_tbl_code='pj_situ_pbc_admin', batch_num)
SELECT
    'ver_hc_pj_situ_pbc_admin' AS hc_tbl_name,
    LAST_DAY(TO_DATE('${p_month_yyyymm}','yyyymm')) AS data_date,
    0 AS is_fin_hc,
    (SELECT MAX(batch_num) FROM odps_prd_olver.ver_submit_org_md WHERE sourc_bw = 'pj' AND dt = '${p_month_yyyymm}')
;
