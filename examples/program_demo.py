from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)


sql = """
SET odps.instance.priority=7;

WITH base AS (
    SELECT
        id,
        amount
    FROM ods.loan_detail
    WHERE dt='${p_month}'
),
summary AS (
    SELECT
        id,
        SUM(amount) AS total_amount
    FROM base
    GROUP BY id
)
INSERT OVERWRITE TABLE dws.loan_summary
PARTITION(dt='${p_month}')
SELECT *
FROM summary;
"""


result = (
    ProgramAnalysisService()
    .analyze(sql)
)


print(
    "\n========== RESULT =========="
)

print(
    "Status:",
    result.status.value,
)


if result.program is None:
    print(
        "Failure:",
        result.failure_reason,
    )

    raise SystemExit(1)


program = result.program


print(
    "\n========== PROGRAM =========="
)

print(
    "Statements:",
    len(program.statements),
)

print(
    "Session hints:",
    len(program.session_hints),
)

print(
    "Parameters:",
    len(program.parameters),
)

print(
    "CTEs:",
    len(program.cte_nodes),
)

print(
    "Scopes:",
    len(program.scope_analyses),
)


print(
    "\n========== STATEMENTS =========="
)

for statement in program.statements:
    print(
        f"\n[{statement.index}]",
        statement.kind.value,
    )

    print(
        "CTEs:",
        statement.cte_names,
    )

    if statement.write_target:
        target = (
            statement.write_target
        )

        print(
            "Target:",
            target.table_name,
        )

        print(
            "Strategy:",
            target.strategy.value,
        )

        print(
            "Partitions:",
            [
                {
                    "name": item.name,
                    "value": item.value,
                    "dynamic": (
                        item.is_dynamic
                    ),
                }
                for item
                in target.partition_spec
            ],
        )


print(
    "\n========== PARAMETERS =========="
)

for parameter in program.parameters:
    print(
        parameter.name,
        "occurrences=",
        len(parameter.occurrences),
    )


print(
    "\n========== CTE DAG =========="
)

nodes_by_scope_id = {
    node.scope_id: node
    for node
    in program.cte_nodes
}

for node in program.cte_nodes:
    dependencies = [
        (
            nodes_by_scope_id[
                dependency_id
            ].name
        )
        for dependency_id
        in node.dependency_scope_ids
    ]

    print(
        node.name,
        "<-",
        dependencies,
    )


print(
    "\n========== SCOPES =========="
)

for scope in program.scope_analyses:
    print(
        "\nScope:",
        scope.scope_id,
    )

    print(
        "CTE:",
        scope.cte_name,
    )

    print(
        "Physical sources:",
        scope.facts.source_tables,
    )