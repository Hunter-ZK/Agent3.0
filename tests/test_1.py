from sql_pilot_engine.metadata.ingestion.rebuild import (
    rebuild_metadata_database,
)


result = rebuild_metadata_database(
    metadata_source_path=(
        "data/metadata.xlsx"
    ),

    standards_source_path=(
        "data/字段命名规则资产_V0.1.xlsx"
    ),

    database_path=(
        "data/metadata.db"
    ),

    metadata_source_label=(
        "2026-05"
    ),

    standards_source_label=(
        "V0.1"
    ),
)


print(
    result.metadata.table_count
)

print(
    result.metadata.column_count
)

print(
    result.standards
)