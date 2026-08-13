class FakePlannerModel:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return """
        {
          "tables": [
            "dwd_order_detail"
          ],
          "dimensions": [
            "user_id"
          ],
          "metrics": [
            "total_order_amount"
          ],
          "filters": [],
          "group_by": [
            "user_id"
          ]
        }
        """


class FakeSQLModel:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return """
        SELECT
            user_id,
            SUM(order_amount)
                AS total_order_amount
        FROM dwd_order_detail
        GROUP BY user_id
        """

from sql_pilot_engine.runtime.validation import (
    TrustedSQLResult,
)


class FakeValidator:

    def validate(
        self,
        *,
        sql: str,
        dialect: str,
    ) -> TrustedSQLResult:

        return TrustedSQLResult(
            accepted=True,
            original_sql=sql,
            final_sql=sql,
            status="trusted",
            issue_count=0,
        )


