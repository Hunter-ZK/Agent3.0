from langgraph.checkpoint.serde.jsonplus import (
    JsonPlusSerializer,
)

from sql_pilot_engine.linking.models import (
    LinkedSchema,
    LinkedTable,
)

from sql_pilot_engine.metadata.models import (
    ColumnMetadata,
    TableMetadata,
)


column = ColumnMetadata(
    name="loan_bal_rmb",
    data_type="DECIMAL(22,2)",
)

table = TableMetadata(
    full_name="test_table",
    columns={
        "loan_bal_rmb": column,
    },
)

linked_table = LinkedTable(
    metadata=table,
)

linked_schema = LinkedSchema(
    tables=(
        linked_table,
    ),
)

serializer = JsonPlusSerializer()


objects = {
    "ColumnMetadata": column,
    "columns": table.columns,
    "columns_as_dict": dict(table.columns),
    "TableMetadata": table,
    "LinkedTable": linked_table,
    "LinkedSchema": linked_schema,
}


for name, value in objects.items():
    try:
        serializer.dumps_typed(value)
        print(name, "PASS")
    except Exception as exc:
        print(
            name,
            "FAIL",
            type(exc).__name__,
            str(exc),
        )