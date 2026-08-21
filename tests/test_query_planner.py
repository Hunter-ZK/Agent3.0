from sql_pilot_engine.context.builder import QueryContext
from sql_pilot_engine.generation.planner import QueryPlanner


class FakeModel:
    def generate(self, prompt: str) -> str:
        return """
        {
          "tables": ["dwd_hd_101_cldwdk"],
          "dimensions": ["dt"],
          "metrics": ["tech_loan_balance"],
          "filters": ["is_high_tech_ent_loan_code = '1'"],
          "group_by": ["dt"],
          "requirements": ["计算同比", "计算环比"]
        }
        """


def test_planner_preserves_requirements():
    planner = QueryPlanner(model=FakeModel())

    context = QueryContext(
        question="统计高新技术企业贷款余额同比及环比情况",
        semantic_context="TABLE dwd_hd_101_cldwdk",
        business_knowledge=(),
        verified_sql=(),
    )

    plan = planner.plan(
        query_context=context,
    )

    assert plan.requirements == (
        "计算同比",
        "计算环比",
    )
