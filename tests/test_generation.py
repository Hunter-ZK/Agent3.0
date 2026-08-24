from sql_pilot_engine.context.builder import QueryContext
from sql_pilot_engine.generation.planner import QueryPlanner
from sql_pilot_engine.generation.sql_generator import SQLGenerator


class FakePlannerModel:
    def generate(self, prompt: str) -> str:
        return """
        {
          "tables": ["dwd_order_detail"],
          "dimensions": ["user_id"],
          "metrics": ["total_order_amount"],
          "filters": [],
          "group_by": ["user_id"]
        }
        """


class FakeSQLModel:
    def generate(self, prompt: str) -> str:
        return """
        SELECT
            user_id,
            SUM(order_amount) AS total_order_amount
        FROM dwd_order_detail
        GROUP BY user_id
        """


def build_context() -> QueryContext:
    return QueryContext(
        question="统计每个用户订单总金额",
        semantic_context="TABLE dwd_order_detail",
        business_knowledge=(),
        verified_sql=(),
    )


def test_query_planner_builds_plan():
    context = build_context()
    planner = QueryPlanner(model=FakePlannerModel())

    plan = planner.plan(
        query_context=context,
    )

    assert plan.tables == ("dwd_order_detail",)
    assert plan.dimensions == ("user_id",)
    assert plan.metrics == ("total_order_amount",)
    assert plan.group_by == ("user_id",)


def test_sql_generator_generates_sql():
    context = build_context()
    planner = QueryPlanner(model=FakePlannerModel())
    plan = planner.plan(query_context=context)

    generator = SQLGenerator(model=FakeSQLModel())

    result = generator.generate(
        plan=plan,
        query_context=context,
    )

    assert "SELECT" in result.sql.upper()
    assert "DWD_ORDER_DETAIL" in result.sql.upper()
    assert "GROUP BY USER_ID" in result.sql.upper()


class FencedSQLModel:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return """```sql
SELECT
    user_id,
    SUM(order_amount) AS total_order_amount
FROM dwd_order_detail
GROUP BY user_id
```"""


def test_sql_generator_strips_outer_sql_fence():

    context = build_context()

    planner = QueryPlanner(
        model=FakePlannerModel()
    )

    plan = planner.plan(
        query_context=context
    )

    generator = SQLGenerator(
        model=FencedSQLModel()
    )

    result = generator.generate(
        plan=plan,
        query_context=context,
    )

    assert not result.sql.startswith(
        "```"
    )

    assert not result.sql.endswith(
        "```"
    )

    assert (
        "SELECT"
        in result.sql.upper()
    )


class InternalBacktickSQLModel:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return (
            "SELECT `user_id` "
            "FROM dwd_order_detail"
        )


def test_sql_generator_keeps_internal_backticks():

    context = build_context()

    planner = QueryPlanner(
        model=FakePlannerModel()
    )

    plan = planner.plan(
        query_context=context
    )

    generator = SQLGenerator(
        model=InternalBacktickSQLModel()
    )

    result = generator.generate(
        plan=plan,
        query_context=context,
    )

    assert "`user_id`" in result.sql