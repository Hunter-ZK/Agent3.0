from __future__ import annotations

from sql_pilot_engine.core.execution_context import SQLExecutionContext
from sql_pilot_engine.evidence.program_context import ProgramEvidenceContextBuilder
from sql_pilot_engine.generation.program_generator import ProductionProgramGenerator
from sql_pilot_engine.llm.fixer import LLMFixer
from sql_pilot_engine.llm.optimizer import LLMOptimizer
from sql_pilot_engine.services.explain_service import ExplainService
from sql_pilot_engine.spec.models import (
    FixedReportField,
    FixedReportPartition,
    FixedReportSpec,
    FixedReportWriteTarget,
)


SUGGESTION = {
    "category": "filter_pushdown",
    "priority": "medium",
    "description": "局部过滤条件前移",
    "reason": "减少中间数据",
    "expected_benefit": "可能减少扫描后的中间行数",
    "risk": "需验证语义等价",
    "requires_execution_validation": True,
}


class _CaptureModel:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system_prompt = ""
        self.user_prompt = ""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = json_schema
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.payload


class _SequenceModel:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, str]] = []

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        _ = json_schema
        self.calls.append((system_prompt, user_prompt))
        if not self.payloads:
            raise AssertionError("Unexpected extra model call")
        return self.payloads.pop(0)


def _build_large_existing_program() -> str:
    ctes = [
        """
base AS (
    SELECT /*+ MAPJOIN(d) */
        f.id,
        f.region,
        f.amount,
        f.tags,
        f.batch_num
    FROM project_src.fact_large f
    LEFT JOIN project_src.dim_small d
        ON f.id = d.id
    WHERE f.dt = '202609'
      AND f.amount > 0
)
""".strip(),
        """
exploded AS (
    SELECT
        id,
        region,
        amount,
        batch_num,
        tag
    FROM base
    LATERAL VIEW EXPLODE(SPLIT(tags, ',')) e AS tag
)
""".strip(),
        """
grouped AS (
    SELECT
        region,
        batch_num,
        SUM(amount) AS total_amount
    FROM exploded
    GROUP BY GROUPING SETS (
        (region, batch_num),
        (batch_num)
    )
)
""".strip(),
        """
unioned AS (
    SELECT
        region,
        total_amount,
        batch_num
    FROM grouped
    WHERE region IS NOT NULL

    UNION ALL

    SELECT
        'ALL' AS region,
        total_amount,
        batch_num
    FROM grouped
    WHERE region IS NULL
)
""".strip(),
    ]

    previous = "unioned"
    for index in range(4, 35):
        name = f"stage_{index:02d}"
        ctes.append(
            f"""
{name} AS (
    SELECT
        region,
        total_amount,
        batch_num
    FROM {previous}
)
""".strip()
        )
        previous = name

    first_statement = (
        "SET odps.sql.type.system.odps2 = true;\n\n"
        "WITH\n"
        + ",\n".join(ctes)
        + f"""

INSERT OVERWRITE TABLE project_dwd.scale_result
PARTITION(dt='202609', batch_num)
SELECT
    region,
    total_amount,
    batch_num
FROM {previous}
;
"""
    )

    second_statement = """
WITH
secondary_base AS (
    SELECT
        id,
        amount
    FROM project_src.fact_large
    WHERE dt = '202609'
),
secondary_agg AS (
    SELECT
        COUNT(*) AS row_count
    FROM secondary_base
)
INSERT OVERWRITE TABLE project_dwd.scale_audit
PARTITION(dt='202609')
SELECT
    row_count
FROM secondary_agg
;
"""

    # Keep the benchmark over the production one-shot rewrite threshold without
    # embedding any real business SQL or data in the repository.
    padding = "\n".join(
        f"-- synthetic production padding {index:03d} " + ("x" * 96)
        for index in range(180)
    )

    sql = first_statement + "\n" + second_statement + "\n" + padding
    assert len(sql) > 16000
    return sql


def _explain_payload() -> dict:
    return {
        "sql_summary": "Synthetic production-scale program",
        "business_purpose": "规模级能力验证",
        "main_tables": [{"table": "hallucinated.table"}],
        "output_columns": [{"target": "hallucinated.column"}],
        "cte_steps": [{"name": "hallucinated_cte"}],
        "cte_dependencies": [],
        "suspicious_points": [],
        "uncertainties": [],
        "route_signals": {},
    }


def test_production_scale_program_context_and_explain_are_stable() -> None:
    sql = _build_large_existing_program()
    context = ProgramEvidenceContextBuilder().build(sql)
    payload = context.to_prompt_payload()

    # SQLProgram counts the leading SET as a real program statement:
    # 1 SET + 2 INSERT statements.
    assert context.statement_count == 3
    assert context.cte_count == 37
    assert context.scope_count > context.cte_count
    assert {item.name for item in context.hints} == {"MAPJOIN"}
    assert set(payload["program"]["read_tables"]) == {
        "project_src.dim_small",
        "project_src.fact_large",
    }
    assert {
        item["table"]
        for item in payload["program"]["write_targets"]
    } == {
        "project_dwd.scale_result",
        "project_dwd.scale_audit",
    }

    model = _CaptureModel(_explain_payload())
    response = ExplainService(llm_client=model).explain(
        SQLExecutionContext(
            sql=sql,
            enable_llm=True,
        )
    )

    assert response.success is True
    assert len(response.cte_steps) == 37
    assert {
        "project_dwd.scale_result",
        "project_dwd.scale_audit",
    } <= {item["table"] for item in response.main_tables}
    assert all(
        item.get("table") != "hallucinated.table"
        for item in response.main_tables
    )
    assert "SQL EXCERPT TRUNCATED" in model.user_prompt


def test_production_scale_fix_and_optimize_use_scoped_patch_by_default() -> None:
    sql = _build_large_existing_program()

    fix_model = _CaptureModel(
        {
            "patches": [
                {
                    "old_sql": "f.amount > 0",
                    "new_sql": "f.amount >= 0",
                    "reason": "synthetic boundary correction",
                }
            ],
            "manual_notes": [],
        }
    )
    fixed = LLMFixer(client=fix_model).fix(
        original_sql=sql,
        deterministic_pre_fix_sql=sql,
        review_issues_text="synthetic boundary issue",
        analysis_context_text="analysis",
        metadata_context_text="metadata",
        program_evidence_context_text="program evidence",
    )

    assert fixed.source == "llm_patch"
    assert "f.amount >= 0" in fixed.fixed_sql
    assert "f.amount > 0" not in fixed.fixed_sql
    assert "scoped patch planner" in fix_model.system_prompt

    optimize_model = _CaptureModel(
        {
            "summary": "Synthetic scoped optimization",
            "suggestions": [SUGGESTION],
            "patches": [
                {
                    "old_sql": "f.amount > 0",
                    "new_sql": "f.amount >= 1",
                    "reason": "synthetic integer boundary rewrite",
                }
            ],
            "rewrite_reason": "局部表达式优化",
            "assumptions": ["amount 为整数"],
            "confidence": 0.8,
        }
    )
    optimized = LLMOptimizer(client=optimize_model).optimize(
        sql=sql,
        dialect="maxcompute",
        optimization_goals=["reduce intermediate rows"],
        analysis_context_text="analysis",
        metadata_context_text="metadata",
        explain_context_text="explain",
        program_evidence_context_text="program evidence",
    )

    assert optimized.candidate_sql is not None
    assert "f.amount >= 1" in optimized.candidate_sql
    assert "scoped patch planner" in optimize_model.system_prompt


def _scale_spec() -> FixedReportSpec:
    return FixedReportSpec(
        report_name="synthetic_scale_report",
        business_requirement="构造双目标生产级 SQL Program 进行规模验收",
        source_tables=("project_src.fact_large",),
        write_targets=(
            FixedReportWriteTarget(
                table_name="project_dwd.scale_result",
                fields=(
                    FixedReportField("id", "标识"),
                    FixedReportField("amount", "金额"),
                ),
                partitions=(
                    FixedReportPartition("dt", "'${p_month}'"),
                    FixedReportPartition("batch_num"),
                ),
            ),
            FixedReportWriteTarget(
                table_name="project_dwd.scale_audit",
                fields=(
                    FixedReportField("row_count", "记录数"),
                ),
                partitions=(
                    FixedReportPartition("dt", "'${p_month}'"),
                ),
            ),
        ),
        parameters=("p_month",),
        session_settings=(("odps.sql.type.system.odps2", "true"),),
        constraints=("不得改变写入目标和分区策略",),
    )


def _scale_plan() -> dict:
    ctes = []
    for index in range(35):
        name = f"stage_{index:02d}"
        if index == 0:
            dependencies = []
            source_tables = ["project_src.fact_large"]
        else:
            dependencies = [f"stage_{index - 1:02d}"]
            source_tables = []

        ctes.append(
            {
                "name": name,
                "purpose": f"synthetic stage {index}",
                "dependencies": dependencies,
                "source_tables": source_tables,
                "output_columns": ["id", "amount", "batch_num"],
            }
        )

    return {
        "statements": [
            {
                "target_index": 0,
                "purpose": "生成主结果",
                "ctes": ctes,
                "final_select_purpose": "输出主结果目标字段",
                "final_dependencies": ["stage_34"],
                "final_source_tables": [],
            },
            {
                "target_index": 1,
                "purpose": "生成审计结果",
                "ctes": [
                    {
                        "name": "audit_base",
                        "purpose": "读取审计源",
                        "dependencies": [],
                        "source_tables": ["project_src.fact_large"],
                        "output_columns": ["id"],
                    }
                ],
                "final_select_purpose": "输出审计记录数",
                "final_dependencies": ["audit_base"],
                "final_source_tables": [],
            },
        ],
        "assumptions": ["synthetic planner assumption"],
    }


def _scale_stage_payloads() -> list[dict]:
    payloads: list[dict] = [_scale_plan()]

    for index in range(35):
        if index == 0:
            select_sql = (
                "SELECT id, amount, batch_num "
                "FROM project_src.fact_large"
            )
        else:
            select_sql = (
                "SELECT id, amount, batch_num "
                f"FROM stage_{index - 1:02d}"
            )
        payloads.append(
            {
                "select_sql": select_sql,
                "assumptions": (
                    ["synthetic stage assumption"]
                    if index == 17
                    else []
                ),
            }
        )

    payloads.append(
        {
            "select_sql": (
                "SELECT id, amount, batch_num FROM stage_34"
            ),
            "assumptions": ["synthetic final assumption"],
        }
    )
    payloads.append(
        {
            "select_sql": "SELECT id FROM project_src.fact_large",
            "assumptions": [],
        }
    )
    payloads.append(
        {
            "select_sql": "SELECT COUNT(*) AS row_count FROM audit_base",
            "assumptions": [],
        }
    )

    return payloads


def test_complex_generate_handles_35_stage_two_target_program() -> None:
    model = _SequenceModel(_scale_stage_payloads())
    result = ProductionProgramGenerator(model=model).generate(
        spec=_scale_spec()
    )

    assert result.success is True
    assert result.candidate_sql is not None
    assert result.candidate_sql.count("INSERT OVERWRITE TABLE") == 2
    assert "project_dwd.scale_result" in result.candidate_sql
    assert "project_dwd.scale_audit" in result.candidate_sql
    assert "PARTITION (dt='${p_month}', batch_num)" in result.candidate_sql
    assert len(model.calls) == 39
    assert result.diagnostics == (
        "synthetic planner assumption",
        "synthetic stage assumption",
        "synthetic final assumption",
    )

    context = ProgramEvidenceContextBuilder().build(result.candidate_sql)
    assert context.statement_count == 3
    assert len(context.write_targets) == 2
    assert context.cte_count == 36
