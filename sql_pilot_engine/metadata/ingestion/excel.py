from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from sql_pilot_engine.metadata.models import (
    MetadataColumnSnapshot,
    MetadataSnapshot,
    MetadataTableSnapshot,
)


REQUIRED_COLUMNS = {
    "字段英文",
    "字段中文",
    "英文表名",
    "中文表名",
}


KNOWN_LAYERS = {
    "ods",
    "dim",
    "dwd",
    "dws",
    "ads",
    "ver",
}


@dataclass(
    frozen=True,
    slots=True,
)
class ExcelMetadataLoadResult:
    snapshot: MetadataSnapshot

    raw_rows: int

    accepted_rows: int

    duplicate_rows: int

    skipped_rows: int


def _clean(
    value,
) -> str:

    if value is None:
        return ""

    return str(value).strip()


def _infer_layer(
    table_name: str,
) -> str:

    prefix = (
        table_name
        .strip()
        .lower()
        .split(
            "_",
            1,
        )[0]
    )

    if prefix in KNOWN_LAYERS:
        return prefix

    return ""


def load_metadata_excel(
    path: str | Path,
    *,
    snapshot_label: str,
    source_name: str | None = None,
) -> ExcelMetadataLoadResult:

    source_path = Path(path)

    workbook = load_workbook(
        source_path,
        read_only=True,
        data_only=True,
    )

    sheet = (
        workbook[
            "每个表的字段"
        ]
        if "每个表的字段"
        in workbook.sheetnames
        else workbook.active
    )

    rows = sheet.iter_rows(
        values_only=True
    )

    headers = tuple(
        _clean(value)
        for value
        in next(rows)
    )

    index = {
        header: position
        for position, header
        in enumerate(headers)
    }

    missing = (
        REQUIRED_COLUMNS
        - set(index)
    )

    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    # {
    #   table_name: {
    #       descriptions: set[str],
    #       columns: {
    #           column_name: {
    #               descriptions: set[str],
    #               ordinal_position: int
    #           }
    #       }
    #   }
    # }
    tables: dict[
        str,
        dict,
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

        column_name = _clean(
            row[
                index["字段英文"]
            ]
        )

        column_description = (
            _clean(
                row[
                    index["字段中文"]
                ]
            )
        )

        table_name = _clean(
            row[
                index["英文表名"]
            ]
        )

        table_description = (
            _clean(
                row[
                    index["中文表名"]
                ]
            )
        )

        if (
            not table_name
            or not column_name
        ):
            skipped_rows += 1
            continue

        normalized_table = (
            table_name.lower()
        )

        normalized_column = (
            column_name.lower()
        )

        record = (
            normalized_table,
            normalized_column,
            table_description,
            column_description,
        )

        if record in seen_records:
            duplicate_rows += 1
            continue

        seen_records.add(record)

        accepted_rows += 1

        table_data = tables.setdefault(
            normalized_table,
            {
                "descriptions": set(),
                "columns": {},
            },
        )

        if table_description:
            table_data[
                "descriptions"
            ].add(
                table_description
            )

        columns = table_data[
            "columns"
        ]

        column_data = columns.setdefault(
            normalized_column,
            {
                "descriptions": set(),

                # 第一次出现的位置，
                # 作为当前快照中的近似字段顺序。
                "ordinal_position": (
                    len(columns) + 1
                ),
            },
        )

        if column_description:
            column_data[
                "descriptions"
            ].add(
                column_description
            )

    table_snapshots = []

    for table_name in sorted(
        tables
    ):

        table_data = tables[
            table_name
        ]

        columns = tuple(
            MetadataColumnSnapshot(
                name=column_name,

                descriptions=tuple(
                    sorted(
                        column_data[
                            "descriptions"
                        ]
                    )
                ),

                # 当前Excel未提供：
                data_type="",
                nullable=None,
                is_partition=None,

                ordinal_position=(
                    column_data[
                        "ordinal_position"
                    ]
                ),
            )
            for (
                column_name,
                column_data,
            )
            in sorted(
                table_data[
                    "columns"
                ].items(),
                key=lambda item: (
                    item[1][
                        "ordinal_position"
                    ]
                ),
            )
        )

        table_snapshots.append(
            MetadataTableSnapshot(
                full_name=table_name,

                descriptions=tuple(
                    sorted(
                        table_data[
                            "descriptions"
                        ]
                    )
                ),

                layer=(
                    _infer_layer(
                        table_name
                    )
                ),

                columns=columns,
            )
        )

    snapshot = MetadataSnapshot(
        source_name=(
            source_name
            or source_path.name
        ),

        snapshot_label=(
            snapshot_label
        ),

        tables=tuple(
            table_snapshots
        ),
    )

    return ExcelMetadataLoadResult(
        snapshot=snapshot,

        raw_rows=raw_rows,

        accepted_rows=accepted_rows,

        duplicate_rows=duplicate_rows,

        skipped_rows=skipped_rows,
    )