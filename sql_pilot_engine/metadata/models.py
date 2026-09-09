from __future__ import annotations

from collections.abc import Mapping

from enum import Enum
from types import MappingProxyType

from dataclasses import dataclass



class MetadataLookupStatus(str, Enum):
    """元数据查询结果状态。

    FOUND：
        已找到目标表，并返回完整元数据。

    NOT_FOUND：
        元数据源正常工作，但确认目标表不存在。

    ERROR：
        元数据查询过程失败，例如网络异常、权限不足。
        ERROR不能等同于表不存在。
    """
    
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PhysicalColumnRef:
    """
    一个 canonical 物理字段身份。

    与 analysis.facts.ColumnReference 不同：

    ColumnReference:
        表示 SQL 中出现的字段引用，
        qualifier 可能只是 alias。

    PhysicalColumnRef:
        表示权威 Metadata 中的物理字段，
        必须使用 canonical physical table name。
    """
    table_full_name: str
    column_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "table_full_name",
            self.table_full_name.strip().lower(),
        )

        object.__setattr__(
            self,
            "column_name",
            self.column_name.strip().lower(),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnMetadata:
    """权威字段 Metadata。"""

    name: str

    technical: ColumnTechnicalMetadata
    business: ColumnBusinessMetadata
    semantic: ColumnSemanticMetadata
    management: ColumnManagementMetadata

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            self.name.strip().lower(),
        )

@dataclass(
    frozen=True,
    slots=True,
)
class ColumnTechnicalMetadata:
    """字段技术元数据。"""

    ordinal_position: int
    data_type: str

    nullable: bool | None = None
    is_partition: bool = False

    declared_upstream_columns: tuple[
        PhysicalColumnRef,
        ...,
    ] = ()

    processing_kind: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_type",
            self.data_type.strip().lower(),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnBusinessMetadata:
    """字段业务元数据。"""

    description: str = ""

    definition: str | None = None
    collection_rule: str | None = None
    validation_rule: str | None = None
    processing_logic: str | None = None

    data_format: str | None = None
    unit: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnSemanticMetadata:
    """字段标准及语义元数据。"""

    is_code_field: bool = False
    code_table_id: str | None = None

    is_dimension: bool = False
    dimension_table: str | None = None
    dimension_column: str | None = None

    is_metric: bool = False
    metric_formula: str | None = None
    metric_aggregation: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class ColumnManagementMetadata:
    """字段管理与血缘登记元数据。"""

    lineage_source: str | None = None

    lineage_confirmation_status: (
        str | None
    ) = None

    remark: str | None = None

@dataclass(
    frozen=True,
    slots=True,
)
class TableMetadata:
    """权威物理表 Metadata。"""

    full_name: str

    technical: TableTechnicalMetadata
    business: TableBusinessMetadata
    operational: TableOperationalMetadata
    management: TableManagementMetadata

    columns: Mapping[
        str,
        ColumnMetadata,
    ]

    def __post_init__(self) -> None:
        normalized_full_name = (
            self.full_name
            .strip()
            .lower()
        )

        expected_full_name = (
            f"{self.technical.project}."
            f"{self.technical.table_name}"
            if self.technical.project
            else self.technical.table_name
        )

        if (
            normalized_full_name
            != expected_full_name
        ):
            raise ValueError(
                "TableMetadata full_name "
                "does not match technical "
                "project/table_name: "
                f"{normalized_full_name!r} "
                "!= "
                f"{expected_full_name!r}"
            )

        normalized_columns: dict[
            str,
            ColumnMetadata,
        ] = {}

        for key, column in (
            self.columns.items()
        ):
            normalized_key = (
                key.strip().lower()
            )

            if (
                normalized_key
                != column.name
            ):
                raise ValueError(
                    "Column mapping key "
                    "does not match "
                    "ColumnMetadata.name: "
                    f"{normalized_key!r} "
                    "!= "
                    f"{column.name!r}"
                )

            if (
                normalized_key
                in normalized_columns
            ):
                raise ValueError(
                    "Duplicate metadata "
                    "column: "
                    f"{normalized_key!r}"
                )

            normalized_columns[
                normalized_key
            ] = column

        partition_fields = set(
            self.technical.partition_fields
        )

        missing_partition_fields = (
            partition_fields
            - set(normalized_columns)
        )

        if missing_partition_fields:
            raise ValueError(
                "Partition fields are "
                "missing from columns: "
                f"{sorted(missing_partition_fields)!r}"
            )

        if (
            self.technical.column_count
            and self.technical.column_count
            != len(normalized_columns)
        ):
            raise ValueError(
                "Metadata column_count "
                "does not match loaded "
                "columns: "
                f"{self.technical.column_count} "
                "!= "
                f"{len(normalized_columns)}"
            )

        object.__setattr__(
            self,
            "full_name",
            normalized_full_name,
        )

        object.__setattr__(
            self,
            "columns",
            MappingProxyType(
                normalized_columns
            ),
        )

    def get_column(
        self,
        column_name: str,
    ) -> ColumnMetadata | None:
        return self.columns.get(
            column_name.strip().lower()
        )

    def column_names(
        self,
    ) -> set[str]:
        return set(self.columns)

    @property
    def is_partitioned(
        self,
    ) -> bool:
        return bool(
            self.technical.partition_fields
        )

@dataclass(
    frozen=True,
    slots=True,
)
class TableTechnicalMetadata:
    """表技术元数据。"""

    project: str
    table_name: str

    code_path: str | None = None

    partition_fields: tuple[
        str,
        ...,
    ] = ()

    column_count: int = 0

    source_system: str | None = None

    declared_upstream_tables: tuple[
        str,
        ...,
    ] = ()

    processing_node: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "project",
            self.project.strip().lower(),
        )

        object.__setattr__(
            self,
            "table_name",
            self.table_name.strip().lower(),
        )

        object.__setattr__(
            self,
            "partition_fields",
            tuple(
                field.strip().lower()
                for field
                in self.partition_fields
            ),
        )

        object.__setattr__(
            self,
            "declared_upstream_tables",
            tuple(
                table.strip().lower()
                for table
                in self.declared_upstream_tables
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class TableBusinessMetadata:
    """表业务元数据。"""

    description: str = ""

    statistical_regime: str | None = None
    business_name: str | None = None

    related_business: tuple[
        str,
        ...,
    ] = ()

    asset_category: str | None = None
    report_name: str | None = None
    purpose: str | None = None
    grain: str | None = None

    business_key: tuple[
        str,
        ...,
    ] = ()

    owning_department: str | None = None
    data_origin: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class TableOperationalMetadata:
    """表运行元数据。"""

    data_cycle: str | None = None
    schedule_cycle: str | None = None
    update_mode: str | None = None

    data_period_field: str | None = None

    first_period: str | None = None
    latest_period: str | None = None
    period_note: str | None = None

    last_updated_at: str | None = None

    row_count: int | None = None
    size_bytes: int | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class TableManagementMetadata:
    """表管理元数据。"""

    maintainer: str | None = None
    asset_status: str | None = None
    last_verified_at: str | None = None
    remark: str | None = None

@dataclass(frozen=True, slots=True)
class TableLookupResult:
    '''MetadataProvider查询一张表后的统一响应'''
    
    status: MetadataLookupStatus
    
    table: TableMetadata | None = None
    error_message: str | None = None
    
    @classmethod
    def found(
        cls,
        table: TableMetadata,
    ) -> "TableLookupResult":
        
        return cls(
            status=MetadataLookupStatus.FOUND,
            table=table,
        )
    
    @classmethod
    def not_found(
        cls,
    ) -> "TableLookupResult":
        return cls(
            status=MetadataLookupStatus.NOT_FOUND,
        )
        
    @classmethod
    def failed(
        cls,
        error_message: str,
    ) -> "TableLookupResult":
        return cls(
            status=MetadataLookupStatus.ERROR,
            error_message=error_message,
        )
        
