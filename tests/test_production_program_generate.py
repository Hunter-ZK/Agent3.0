from __future__ import annotations

from sql_pilot_engine.generation.program_generator import (
    ProductionProgramGenerator,
)
from sql_pilot_engine.spec.models import (
    FixedReportField,
    FixedReportPartition,
    FixedReportSpec,
    FixedReportWriteTarget,
)


PLAN = {
    "statements": [
        {
            "target_index": 0,
            "purpose": "汇总贷款金额",
            "ctes": [
                {
                    "name": "base",
                    "purpose": "读取贷款明细",
                    "dependencies": [],
                    "source_tables": ["project_src.loan_detail"],
                    "output_columns": ["id", "amount"],
                },
                {
                    "name": "agg",
                    "purpose": "按客户汇总金额",
                    "dependencies": ["base"],
                    "source_tables": [],
                    "output_columns": ["id", "total_amount"],
                },
            ],
            "final_select_purpose": "输出目标字段",
            "final_dependencies": ["agg"],
            "final_source_tables": [],
        }
    ],
    "assumptions": ["planner assumption"],
}


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
            raise AssertionError("Unexpected extra LLM call")
        return self.payloads.pop(0)


def _spec() -> FixedReportSpec:
    return FixedReportSpec(
        report_name="loan_summary",
        business_requirement="按客户汇总贷款金额并写入月度结果表",
        source_tables=("project_src.loan_detail",),
        write_targets=(
            FixedReportWriteTarget(
                table_name="project_dwd.loan_summary",
                fields=(
                    FixedReportField("id", "客户标识"),
                    FixedReportField("total_amount", "贷款金额合计"),
                ),
                partitions=(
                    FixedReportPartition(
                        "dt",
                        "'${p_month}'",
                    ),
                ),
            ),
        ),
        parameters=("p_month",),
        session_settings=(("odps.sql.type.system.odps2", "true"),),
        constraints=("total_amount 为 amount 求和",),
    )


def test_staged_program_generate_keeps_target_partition_and_assumptions_system_owned():
    model = _SequenceModel(
        [
            PLAN,
            {
                "select_sql": (
                    "SELECT id, amount "
                    "FROM project_src.loan_detail"
                ),
                "assumptions": ["base assumption"],
            },
            {
                "select_sql": (
                    "SELECT id, SUM(amount) AS total_amount "
                    "FROM base GROUP BY id"
                ),
                "assumptions": [],
            },
            {
                "select_sql": "SELECT id, total_amount FROM agg",
                "assumptions": ["final assumption"],
            },
        ]
    )

    result = ProductionProgramGenerator(model=model).generate(
        spec=_spec()
    )

    assert result.success is True
    assert result.candidate_sql is not None
    assert "INSERT OVERWRITE TABLE project_dwd.loan_summary" in result.candidate_sql
    assert "PARTITION (dt='${p_month}')" in result.candidate_sql
    assert "WITH\nbase AS" in result.candidate_sql
    assert "agg AS" in result.candidate_sql
    assert "SET odps.sql.type.system.odps2=true;" in result.candidate_sql
    assert result.diagnostics == (
        "planner assumption",
        "base assumption",
        "final assumption",
    )
    assert len(model.calls) == 4


def test_program_plan_cycle_is_rejected_before_stage_generation():
    cyclic = {
        "statements": [
            {
                "target_index": 0,
                "purpose": "bad plan",
                "ctes": [
                    {
                        "name": "a",
                        "purpose": "a",
                        "dependencies": ["b"],
                        "source_tables": [],
                        "output_columns": ["id"],
                    },
                    {
                        "name": "b",
                        "purpose": "b",
                        "dependencies": ["a"],
                        "source_tables": [],
                        "output_columns": ["id"],
                    },
                ],
                "final_select_purpose": "output",
                "final_dependencies": ["a"],
                "final_source_tables": [],
            }
        ],
        "assumptions": [],
    }
    model = _SequenceModel([cyclic])

    result = ProductionProgramGenerator(model=model).generate(
        spec=_spec()
    )

    assert result.success is False
    assert result.candidate_sql is None
    assert "dependency cycle" in result.diagnostics[0]
    assert len(model.calls) == 1


def test_stage_generator_cannot_smuggle_insert_or_ddl():
    model = _SequenceModel(
        [
            PLAN,
            {
                "select_sql": (
                    "INSERT OVERWRITE TABLE project_dwd.evil "
                    "SELECT id FROM project_src.loan_detail"
                ),
                "assumptions": [],
            },
        ]
    )

    result = ProductionProgramGenerator(model=model).generate(
        spec=_spec()
    )

    assert result.success is False
    assert result.candidate_sql is None
    assert "SELECT/query body" in result.diagnostics[0]


def test_planner_cannot_introduce_undeclared_physical_source():
    bad_plan = {
        **PLAN,
        "statements": [
            {
                **PLAN["statements"][0],
                "ctes": [
                    {
                        **PLAN["statements"][0]["ctes"][0],
                        "source_tables": ["project_secret.unknown_table"],
                    }
                ],
                "final_dependencies": ["base"],
            }
        ],
    }
    model = _SequenceModel([bad_plan])

    result = ProductionProgramGenerator(model=model).generate(
        spec=_spec()
    )

    assert result.success is False
    assert result.candidate_sql is None
    assert "undeclared physical sources" in result.diagnostics[0]


def test_final_stage_must_declare_direct_physical_source():
    direct_plan = {
        "statements": [
            {
                "target_index": 0,
                "purpose": "direct output",
                "ctes": [],
                "final_select_purpose": "output",
                "final_dependencies": [],
                "final_source_tables": [],
            }
        ],
        "assumptions": [],
    }
    model = _SequenceModel(
        [
            direct_plan,
            {
                "select_sql": (
                    "SELECT id, SUM(amount) AS total_amount "
                    "FROM project_src.loan_detail GROUP BY id"
                ),
                "assumptions": [],
            },
        ]
    )

    result = ProductionProgramGenerator(model=model).generate(
        spec=_spec()
    )

    assert result.success is False
    assert result.candidate_sql is None
    assert "outside its declared boundary" in result.diagnostics[0]


def test_direct_final_stage_can_use_explicitly_declared_physical_source():
    direct_plan = {
        "statements": [
            {
                "target_index": 0,
                "purpose": "direct output",
                "ctes": [],
                "final_select_purpose": "output",
                "final_dependencies": [],
                "final_source_tables": ["project_src.loan_detail"],
            }
        ],
        "assumptions": [],
    }
    model = _SequenceModel(
        [
            direct_plan,
            {
                "select_sql": (
                    "SELECT id, SUM(amount) AS total_amount "
                    "FROM project_src.loan_detail GROUP BY id"
                ),
                "assumptions": [],
            },
        ]
    )

    result = ProductionProgramGenerator(model=model).generate(
        spec=_spec()
    )

    assert result.success is True
    assert result.candidate_sql is not None


def test_final_projection_count_must_match_target_contract():
    model = _SequenceModel(
        [
            PLAN,
            {
                "select_sql": (
                    "SELECT id, amount "
                    "FROM project_src.loan_detail"
                ),
                "assumptions": [],
            },
            {
                "select_sql": (
                    "SELECT id, SUM(amount) AS total_amount "
                    "FROM base GROUP BY id"
                ),
                "assumptions": [],
            },
            {
                "select_sql": "SELECT id FROM agg",
                "assumptions": [],
            },
        ]
    )

    result = ProductionProgramGenerator(model=model).generate(
        spec=_spec()
    )

    assert result.success is False
    assert result.candidate_sql is None
    assert "projection count" in result.diagnostics[0]
