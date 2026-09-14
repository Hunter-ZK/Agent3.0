from __future__ import annotations

from sql_pilot_engine.metadata.mock_provider import MockMetadataProvider
from sql_pilot_engine.metadata.models import (
    ColumnBusinessMetadata,
    ColumnManagementMetadata,
    ColumnMetadata,
    ColumnSemanticMetadata,
    ColumnTechnicalMetadata,
    TableBusinessMetadata,
    TableManagementMetadata,
    TableMetadata,
    TableOperationalMetadata,
    TableTechnicalMetadata,
)


_TECH_LOAN_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("fin_org_branch_code", "string", "经办金融机构统一社会信用代码"),
    ("fin_org_branch_area_code", "string", "经办金融机构所在地"),
    ("is_high_tech_mfg_loan_code", "string", "是否高新技术企业贷款"),
    ("is_sci_medium_ent_loan_code", "string", "是否科技中小企业贷款"),
    ("loan_bal_rmb", "decimal(22,2)", "贷款余额"),
    ("rate", "decimal(15,5)", "存量贷款利率"),
    ("loan_iou_no", "string", "贷款借据号"),
    ("ent_code", "string", "借款企业统一社会信用代码"),
    ("loan_grant_date", "string", "贷款发放日期"),
    ("loan_due_date", "string", "贷款到期日期"),
    ("fin_org_code", "string", "金融法人机构统一社会信用代码"),
    ("fin_org_type_code", "string", "金融法人机构类型"),
    ("data_date", "string", "数据报送日期"),
    ("dt", "string", "数据报送日期分区字段"),
)

_GREEN_LOAN_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("fin_org_branch_code", "string", "经办金融机构统一社会信用代码"),
    ("fin_org_branch_area_code", "string", "经办金融机构所在地"),
    ("green_loan_type_code", "string", "绿色贷款类型"),
    ("loan_bal_rmb", "decimal(22,2)", "贷款余额"),
    ("rate", "decimal(15,5)", "存量贷款利率"),
    ("loan_iou_no", "string", "贷款借据号"),
    ("ent_code", "string", "借款企业统一社会信用代码"),
    ("loan_grant_date", "string", "贷款发放日期"),
    ("loan_due_date", "string", "贷款到期日期"),
    ("fin_org_code", "string", "金融法人机构统一社会信用代码"),
    ("fin_org_type_code", "string", "金融法人机构类型"),
    ("data_date", "string", "数据报送日期"),
    ("dt", "string", "数据报送日期分区字段"),
)


def build_loan_demo_metadata_provider() -> MockMetadataProvider:
    """Return deterministic synthetic metadata for public Text-to-SQL demos/tests."""

    return MockMetadataProvider(
        tables=(
            _table(
                full_name="odps_prd_dwd.ods_hd_100_cldkxx",
                description="Synthetic technology-loan detail table for public demos.",
                columns=_TECH_LOAN_COLUMNS,
            ),
            _table(
                full_name="odps_prd_dwd.ods_hd_200_cldkxx",
                description="Synthetic green-loan detail table for public demos.",
                columns=_GREEN_LOAN_COLUMNS,
            ),
        )
    )


def _table(
    *,
    full_name: str,
    description: str,
    columns: tuple[tuple[str, str, str], ...],
) -> TableMetadata:
    project, table_name = full_name.split(".", 1)

    mapped_columns = {
        name: _column(
            name=name,
            ordinal_position=index,
            data_type=data_type,
            description=column_description,
            is_partition=(name == "dt"),
        )
        for index, (name, data_type, column_description) in enumerate(
            columns,
            start=1,
        )
    }

    return TableMetadata(
        full_name=full_name,
        technical=TableTechnicalMetadata(
            project=project,
            table_name=table_name,
            partition_fields=("dt",),
            column_count=len(mapped_columns),
            source_system="synthetic_demo",
        ),
        business=TableBusinessMetadata(
            description=description,
            grain="Synthetic row-level loan detail fixture.",
            data_origin="synthetic_demo",
        ),
        operational=TableOperationalMetadata(
            data_cycle="monthly",
            update_mode="synthetic",
            data_period_field="dt",
        ),
        management=TableManagementMetadata(
            asset_status="synthetic",
            remark="Public demo fixture; not production metadata.",
        ),
        columns=mapped_columns,
    )


def _column(
    *,
    name: str,
    ordinal_position: int,
    data_type: str,
    description: str,
    is_partition: bool,
) -> ColumnMetadata:
    return ColumnMetadata(
        name=name,
        technical=ColumnTechnicalMetadata(
            ordinal_position=ordinal_position,
            data_type=data_type,
            nullable=True,
            is_partition=is_partition,
        ),
        business=ColumnBusinessMetadata(
            description=description,
        ),
        semantic=ColumnSemanticMetadata(
            is_dimension=(name in {"fin_org_branch_area_code", "fin_org_type_code", "dt"}),
        ),
        management=ColumnManagementMetadata(
            remark="Synthetic demo column.",
        ),
    )
