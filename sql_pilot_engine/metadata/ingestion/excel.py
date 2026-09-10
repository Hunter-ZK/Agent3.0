from __future__ import annotations

import sqlite3

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from sql_pilot_engine.metadata.ingestion.writer import (
    write_metadata_tables,
)

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

from sql_pilot_engine.metadata.schema import (
    MetadataProvenance,
)


LEGACY_FORMAT_NAME = (
    "legacy_4_column"
)


LEGACY_REQUIRED_COLUMNS = {
    "字段英文",
    "字段中文",
    "英文表名",
    "中文表名",
}


LEGACY_PREFERRED_SHEET = (
    "每个表的字段"
)


@dataclass(
    frozen=True,
    slots=True,
)
class ExcelMetadataImportResult:
    """
    一次 Excel Metadata Import 的结果摘要。

    provenance：
        描述本次 Excel Source 的可信等级。

    source_format：
        描述本次识别到的外部文件格式。

    注意：
        provenance 是 build-level fact，
        不进入 TableLookupResult。
    """

    table_count: int
    column_count: int

    raw_rows: int
    accepted_rows: int
    duplicate_rows: int
    skipped_rows: int

    provenance: MetadataProvenance
    source_format: str


@dataclass(
    frozen=True,
    slots=True,
)
class _LegacyParseResult:
    """
    Legacy Excel Adapter 的内部结果。

    前导下划线表示：

    这不是 Metadata Domain Contract，
    只是 Excel Adapter 内部临时结构。
    """

    tables: tuple[
        TableMetadata,
        ...,
    ]

    raw_rows: int
    accepted_rows: int
    duplicate_rows: int
    skipped_rows: int


def _clean(
    value: object,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _primary_description(
    counter: Counter[str],
) -> str:
    """
    一个物理对象仍然只保留一个主中文描述。

    Legacy 文件中如果同一对象存在多个描述：

    1. 选择出现次数最多的；
    2. 次数一致时选择最早出现的。

    这是旧 Metadata Import 既有规则，
    本轮不改变其业务含义。
    """

    if not counter:
        return ""

    return (
        counter
        .most_common(1)[0][0]
    )


def import_metadata_excel(
    source_path: str | Path,
    database_path: str | Path,
) -> ExcelMetadataImportResult:
    """
    Excel Metadata 的统一入口。

    当前能够确认的实际格式只有：

        legacy_4_column

    即：

        字段英文
        字段中文
        英文表名
        中文表名

    未来正式盘点模板接入时，
    在这里增加新的 Adapter Dispatch。

    Persistence Writer 不需要改变。
    """

    source = Path(
        source_path
    )

    database = Path(
        database_path
    )

    if not source.exists():
        raise FileNotFoundError(
            source
        )

    parse_result = (
        _parse_legacy_excel(
            source
        )
    )

    with sqlite3.connect(
        database
    ) as connection:

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        (
            table_count,
            column_count,
        ) = (
            write_metadata_tables(
                connection,
                parse_result.tables,
            )
        )

    return ExcelMetadataImportResult(
        table_count=table_count,
        column_count=column_count,

        raw_rows=(
            parse_result.raw_rows
        ),

        accepted_rows=(
            parse_result
            .accepted_rows
        ),

        duplicate_rows=(
            parse_result
            .duplicate_rows
        ),

        skipped_rows=(
            parse_result
            .skipped_rows
        ),

        provenance=(
            MetadataProvenance
            .PARTIAL
        ),

        source_format=(
            LEGACY_FORMAT_NAME
        ),
    )


def _parse_legacy_excel(
    source: Path,
) -> _LegacyParseResult:
    """
    Legacy Excel Adapter。

    External representation
        ↓
    TableMetadata[]

    本函数不执行任何 SQLite INSERT。
    """

    workbook = load_workbook(
        source,
        read_only=True,
        data_only=True,
    )

    try:

        if (
            LEGACY_PREFERRED_SHEET
            in workbook.sheetnames
        ):
            sheet = workbook[
                LEGACY_PREFERRED_SHEET
            ]
        else:
            sheet = (
                workbook.active
            )

        rows = sheet.iter_rows(
            values_only=True
        )

        try:
            header_row = next(
                rows
            )
        except StopIteration as exc:
            raise ValueError(
                "Metadata Excel is empty."
            ) from exc

        headers = tuple(
            _clean(value)
            for value
            in header_row
        )

        column_indexes = {
            name: index
            for index, name
            in enumerate(headers)
            if name
        }

        missing_columns = (
            LEGACY_REQUIRED_COLUMNS
            - set(column_indexes)
        )

        if missing_columns:
            raise ValueError(
                "Unsupported metadata Excel "
                "format. "
                "The current adapter only "
                "recognizes legacy_4_column. "
                "Missing columns: "
                + ", ".join(
                    sorted(
                        missing_columns
                    )
                )
            )

        # ----------------------------------------------
        # Legacy Source Aggregation
        #
        # 这里只存在于 Adapter 内部，
        # 不作为 Runtime Cache。
        # ----------------------------------------------

        tables: dict[
            str,
            dict[str, object],
        ] = {}

        seen_records: set[
            tuple[
                str,
                str,
                str,
                str,
            ]
        ] = set()

        raw_rows = 0
        accepted_rows = 0
        duplicate_rows = 0
        skipped_rows = 0

        for row in rows:

            raw_rows += 1

            column_name = _cell(
                row,
                column_indexes[
                    "字段英文"
                ],
            )

            column_description = _cell(
                row,
                column_indexes[
                    "字段中文"
                ],
            )

            table_name = _cell(
                row,
                column_indexes[
                    "英文表名"
                ],
            )

            table_description = _cell(
                row,
                column_indexes[
                    "中文表名"
                ],
            )

            if (
                not table_name
                or not column_name
            ):
                skipped_rows += 1
                continue

            normalized_table_name = (
                table_name.lower()
            )

            normalized_column_name = (
                column_name.lower()
            )

            record = (
                normalized_table_name,
                normalized_column_name,
                table_description,
                column_description,
            )

            if record in seen_records:
                duplicate_rows += 1
                continue

            seen_records.add(
                record
            )

            accepted_rows += 1

            table_data = (
                tables.setdefault(
                    normalized_table_name,
                    {
                        "descriptions": (
                            Counter()
                        ),
                        "columns": {},
                    },
                )
            )

            descriptions = (
                table_data[
                    "descriptions"
                ]
            )

            if not isinstance(
                descriptions,
                Counter,
            ):
                raise TypeError(
                    "Internal legacy "
                    "adapter error."
                )

            if table_description:
                descriptions[
                    table_description
                ] += 1

            raw_columns = (
                table_data[
                    "columns"
                ]
            )

            if not isinstance(
                raw_columns,
                dict,
            ):
                raise TypeError(
                    "Internal legacy "
                    "adapter error."
                )

            if (
                normalized_column_name
                not in raw_columns
            ):
                raw_columns[
                    normalized_column_name
                ] = {
                    "descriptions": (
                        Counter()
                    ),

                    "ordinal_position": (
                        len(raw_columns)
                        + 1
                    ),
                }

            column_data = (
                raw_columns[
                    normalized_column_name
                ]
            )

            if not isinstance(
                column_data,
                dict,
            ):
                raise TypeError(
                    "Internal legacy "
                    "adapter error."
                )

            column_descriptions = (
                column_data[
                    "descriptions"
                ]
            )

            if not isinstance(
                column_descriptions,
                Counter,
            ):
                raise TypeError(
                    "Internal legacy "
                    "adapter error."
                )

            if column_description:
                column_descriptions[
                    column_description
                ] += 1

        domain_tables = (
            _build_legacy_domain_tables(
                tables
            )
        )

        return _LegacyParseResult(
            tables=domain_tables,

            raw_rows=raw_rows,
            accepted_rows=(
                accepted_rows
            ),
            duplicate_rows=(
                duplicate_rows
            ),
            skipped_rows=(
                skipped_rows
            ),
        )

    finally:
        workbook.close()


def _cell(
    row: tuple[object, ...],
    index: int,
) -> str:
    """
    安全读取 Excel Row。

    某些 Excel 行尾可能比 Header 短，
    这种情况按空单元格处理。
    """

    if index >= len(row):
        return ""

    return _clean(
        row[index]
    )


def _build_legacy_domain_tables(
    tables: dict[
        str,
        dict[str, object],
    ],
) -> tuple[
    TableMetadata,
    ...,
]:
    """
    Legacy aggregate
        ↓
    Agent3 Metadata Domain

    Legacy Source 没有：

    - project
    - data_type
    - partition
    - row_count
    - lineage
    - business metadata

    因此：

        project = ""
        data_type = ""
        provenance = PARTIAL

    绝不猜测这些事实。
    """

    result: list[
        TableMetadata
    ] = []

    for (
        table_name,
        table_data,
    ) in tables.items():

        descriptions = (
            table_data[
                "descriptions"
            ]
        )

        raw_columns = (
            table_data[
                "columns"
            ]
        )

        if (
            not isinstance(
                descriptions,
                Counter,
            )
            or not isinstance(
                raw_columns,
                dict,
            )
        ):
            raise TypeError(
                "Internal legacy "
                "adapter error."
            )

        columns: dict[
            str,
            ColumnMetadata,
        ] = {}

        for (
            column_name,
            raw_column_data,
        ) in raw_columns.items():

            if not isinstance(
                raw_column_data,
                dict,
            ):
                raise TypeError(
                    "Internal legacy "
                    "adapter error."
                )

            column_descriptions = (
                raw_column_data[
                    "descriptions"
                ]
            )

            ordinal_position = int(
                raw_column_data[
                    "ordinal_position"
                ]
            )

            if not isinstance(
                column_descriptions,
                Counter,
            ):
                raise TypeError(
                    "Internal legacy "
                    "adapter error."
                )

            columns[
                column_name
            ] = ColumnMetadata(
                name=column_name,

                technical=(
                    ColumnTechnicalMetadata(
                        ordinal_position=(
                            ordinal_position
                        ),

                        # Legacy Source
                        # 没有字段类型。
                        #
                        # 不允许猜。
                        data_type="",

                        nullable=None,
                        is_partition=False,
                    )
                ),

                business=(
                    ColumnBusinessMetadata(
                        description=(
                            _primary_description(
                                column_descriptions
                            )
                        )
                    )
                ),

                semantic=(
                    ColumnSemanticMetadata()
                ),

                management=(
                    ColumnManagementMetadata()
                ),
            )

        result.append(
            TableMetadata(
                # Legacy Source 没有 project，
                # 所以这里只能保留 bare name。
                full_name=table_name,

                technical=(
                    TableTechnicalMetadata(
                        project="",
                        table_name=table_name,

                        partition_fields=(),

                        column_count=(
                            len(columns)
                        ),
                    )
                ),

                business=(
                    TableBusinessMetadata(
                        description=(
                            _primary_description(
                                descriptions
                            )
                        )
                    )
                ),

                operational=(
                    TableOperationalMetadata()
                ),

                management=(
                    TableManagementMetadata()
                ),

                columns=columns,
            )
        )

    return tuple(
        result
    )