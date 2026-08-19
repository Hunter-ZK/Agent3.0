from sql_pilot_engine.metadata.sqlite_repository import (
    SQLiteMetadataRepository,
)


metadata = SQLiteMetadataRepository(
    "data/metadata/agent_metadata.db"
)


print(
    metadata.find_tables(
        "绿色贷款"
    )
)


print(
    metadata.find_columns(
        "贷款余额",
        limit=10,
    )
)


print(
    metadata.find_column_usages(
        "loan_bal_rmb",
        limit=20,
    )
)