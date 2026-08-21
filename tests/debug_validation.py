from sql_pilot_engine.app.factory import (
    build_workflow,
)


sql = """
SELECT
    user_id,
    SUM(order_amount) AS total_order_amount
FROM dwd_order_detail
GROUP BY user_id
"""


workflow = build_workflow(
    max_retries=0
)


result = workflow.run(
    sql
)


print(result)
print(
    vars(result)
    if hasattr(result, "__dict__")
    else result
)