from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

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


class StaticStructuredModel:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system_prompt = ""
        self.user_prompt = ""

    def generate_json(self, system_prompt: str, user_prompt: str, json_schema: dict) -> dict:
        _ = json_schema
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.payload


class SequenceStructuredModel:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls = 0

    def generate_json(self, system_prompt: str, user_prompt: str, json_schema: dict) -> dict:
        _ = system_prompt
        _ = user_prompt
        _ = json_schema
        self.calls += 1
        if not self.payloads:
            raise RuntimeError("Acceptance fixture received an unexpected model call.")
        return self.payloads.pop(0)


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    name: str
    passed: bool
    detail: str


def build_scale_sql() -> str:
    ctes = [
        """base AS (
    SELECT /*+ MAPJOIN(d) */ f.id, f.region, f.amount, f.tags, f.batch_num
    FROM project_src.fact_large f
    LEFT JOIN project_src.dim_small d ON f.id = d.id
    WHERE f.dt = '202609' AND f.amount > 0
)""",
        """exploded AS (
    SELECT id, region, amount, batch_num, tag
    FROM base
    LATERAL VIEW EXPLODE(SPLIT(tags, ',')) e AS tag
)""",
        """grouped AS (
    SELECT region, batch_num, SUM(amount) AS total_amount
    FROM exploded
    GROUP BY GROUPING SETS ((region, batch_num), (batch_num))
)""",
        """unioned AS (
    SELECT region, total_amount, batch_num FROM grouped WHERE region IS NOT NULL
    UNION ALL
    SELECT 'ALL' AS region, total_amount, batch_num FROM grouped WHERE region IS NULL
)""",
    ]

    previous = "unioned"
    for index in range(4, 35):
        name = f"stage_{index:02d}"
        ctes.append(
            f"{name} AS (SELECT region, total_amount, batch_num FROM {previous})"
        )
        previous = name

    padding = (
        "/*\n"
        + "\n".join(
            f"synthetic production padding {index:03d} " + ("x" * 96)
            for index in range(180)
        )
        + "\n*/\n"
    )

    sql = (
        "SET odps.sql.type.system.odps2 = true;\n\n"
        + padding
        + "WITH\n"
        + ",\n".join(ctes)
        + f"""
INSERT OVERWRITE TABLE project_dwd.scale_result
PARTITION(dt='202609', batch_num)
SELECT region, total_amount, batch_num FROM {previous};

WITH secondary_base AS (
    SELECT id, amount FROM project_src.fact_large WHERE dt = '202609'
), secondary_agg AS (
    SELECT COUNT(*) AS row_count FROM secondary_base
)
INSERT OVERWRITE TABLE project_dwd.scale_audit
PARTITION(dt='202609')
SELECT row_count FROM secondary_agg;
"""
    )
    assert len(sql) > 16000
    return sql


def scale_spec() -> FixedReportSpec:
    return FixedReportSpec(
        report_name="synthetic_scale_report",
        business_requirement="构造双目标生产级 SQL Program 进行本地验收",
        source_tables=("project_src.fact_large",),
        write_targets=(
            FixedReportWriteTarget(
                table_name="project_dwd.scale_result",
                fields=(FixedReportField("id"), FixedReportField("amount")),
                partitions=(
                    FixedReportPartition("dt", "'${p_month}'"),
                    FixedReportPartition("batch_num"),
                ),
            ),
            FixedReportWriteTarget(
                table_name="project_dwd.scale_audit",
                fields=(FixedReportField("row_count"),),
                partitions=(FixedReportPartition("dt", "'${p_month}'"),),
            ),
        ),
        parameters=("p_month",),
        session_settings=(("odps.sql.type.system.odps2", "true"),),
        constraints=("不得改变写入目标和分区策略",),
    )


def scale_plan() -> dict:
    ctes = []
    for index in range(35):
        ctes.append(
            {
                "name": f"stage_{index:02d}",
                "purpose": f"synthetic stage {index}",
                "dependencies": [] if index == 0 else [f"stage_{index - 1:02d}"],
                "source_tables": ["project_src.fact_large"] if index == 0 else [],
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


def scale_generation_payloads() -> list[dict]:
    payloads: list[dict] = [scale_plan()]
    for index in range(35):
        source = "project_src.fact_large" if index == 0 else f"stage_{index - 1:02d}"
        payloads.append(
            {
                "select_sql": f"SELECT id, amount, batch_num FROM {source}",
                "assumptions": ["synthetic stage assumption"] if index == 17 else [],
            }
        )
    payloads.extend(
        [
            {
                "select_sql": "SELECT id, amount, batch_num FROM stage_34",
                "assumptions": ["synthetic final assumption"],
            },
            {
                "select_sql": "SELECT id FROM project_src.fact_large",
                "assumptions": [],
            },
            {
                "select_sql": "SELECT COUNT(*) AS row_count FROM audit_base",
                "assumptions": [],
            },
        ]
    )
    return payloads


def run_synthetic_acceptance() -> tuple[list[AcceptanceCheck], dict]:
    checks: list[AcceptanceCheck] = []
    sql = build_scale_sql()

    context = ProgramEvidenceContextBuilder().build(sql)
    payload = context.to_prompt_payload()
    write_targets = payload["program"]["write_targets"]
    context_ok = (
        len(sql) > 16000
        and context.statement_count == 2
        and context.cte_count == 37
        and len(write_targets) == 2
        and {item.name for item in context.hints} == {"MAPJOIN"}
    )
    checks.append(
        AcceptanceCheck(
            "Program / Evidence scale",
            context_ok,
            (
                f"chars={len(sql)}, statements={context.statement_count}, "
                f"ctes={context.cte_count}, scopes={context.scope_count}, "
                f"write_targets={len(write_targets)}"
            ),
        )
    )

    explained = ExplainService().explain(SQLExecutionContext(sql=sql))
    checks.append(
        AcceptanceCheck(
            "Deterministic Explain",
            explained.success and len(explained.cte_steps) == 37,
            explained.sql_summary,
        )
    )

    fix_model = StaticStructuredModel(
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
    checks.append(
        AcceptanceCheck(
            "Scoped Fix",
            fixed.source == "llm_patch" and "f.amount >= 0" in fixed.fixed_sql,
            f"source={fixed.source}, fixes={fixed.applied_fixes}",
        )
    )

    optimize_model = StaticStructuredModel(
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
    checks.append(
        AcceptanceCheck(
            "Scoped Optimize",
            optimized.candidate_sql is not None
            and "f.amount >= 1" in optimized.candidate_sql,
            f"confidence={optimized.confidence}, suggestions={len(optimized.suggestions)}",
        )
    )

    generation_model = SequenceStructuredModel(scale_generation_payloads())
    generated = ProductionProgramGenerator(model=generation_model).generate(spec=scale_spec())
    generated_context = (
        ProgramEvidenceContextBuilder().build(generated.candidate_sql)
        if generated.candidate_sql is not None
        else None
    )
    generation_ok = (
        generated.success
        and generated.candidate_sql is not None
        and generation_model.calls == 39
        and generated_context is not None
        and generated_context.statement_count == 2
        and generated_context.cte_count == 36
    )
    checks.append(
        AcceptanceCheck(
            "35-stage Complex Generate",
            generation_ok,
            (
                f"model_calls={generation_model.calls}, "
                f"trusted_candidate={generated.trusted_candidate}, "
                f"diagnostics={generated.diagnostics}"
            ),
        )
    )

    summary = {
        "synthetic_sql_chars": len(sql),
        "statements": context.statement_count,
        "ctes": context.cte_count,
        "scopes": context.scope_count,
        "read_tables": payload["program"]["read_tables"],
        "write_targets": write_targets,
        "hints": [item.name for item in context.hints],
    }
    return checks, summary


def inspect_local_sql(path: Path) -> dict:
    sql = path.read_text(encoding="utf-8")
    context = ProgramEvidenceContextBuilder().build(sql)
    payload = context.to_prompt_payload()
    explained = ExplainService().explain(SQLExecutionContext(sql=sql))

    return {
        "path": str(path),
        "chars": len(sql),
        "statements": context.statement_count,
        "ctes": context.cte_count,
        "scopes": context.scope_count,
        "read_tables": payload["program"]["read_tables"],
        "write_targets": payload["program"]["write_targets"],
        "hints": [item.name for item in context.hints],
        "diagnostics": [
            {
                "code": item.code,
                "message": item.message,
                "capability": item.capability,
                "severity": item.severity,
            }
            for item in context.diagnostics
        ],
        "explain_summary": explained.sql_summary,
        "explain_success": explained.success,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent3.0 production capability local acceptance"
    )
    parser.add_argument(
        "--sql",
        type=Path,
        default=None,
        help=(
            "Optional local SQL file for deterministic private inspection. "
            "The file is only read locally by this script."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the human acceptance panel.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checks, synthetic_summary = run_synthetic_acceptance()
    local_sql = inspect_local_sql(args.sql) if args.sql is not None else None

    result = {
        "passed": all(item.passed for item in checks),
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail}
            for item in checks
        ],
        "synthetic_summary": synthetic_summary,
        "local_sql": local_sql,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n=== Agent3.0 Production Capability Acceptance ===")
        for item in checks:
            status = "PASS" if item.passed else "FAIL"
            print(f"[{status}] {item.name}")
            print(f"       {item.detail}")

        print("\nSynthetic production-scale summary:")
        print(json.dumps(synthetic_summary, ensure_ascii=False, indent=2))

        if local_sql is not None:
            print("\nLocal SQL deterministic inspection:")
            print(json.dumps(local_sql, ensure_ascii=False, indent=2))

        print("\nOVERALL:", "PASS" if result["passed"] else "FAIL")

    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
