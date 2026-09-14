from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sql_pilot_engine.app.sql_core_factory import build_sql_pilot_engine
from sql_pilot_engine.config.llm import load_deepseek_settings
from sql_pilot_engine.evidence.program_context import ProgramEvidenceContextBuilder
from sql_pilot_engine.generation.production_service import ProductionGenerateService
from sql_pilot_engine.llm.clients import DeepSeekLLMClient
from sql_pilot_engine.llm.transport import OpenAICompatibleTransport
from sql_pilot_engine.metadata.sqlite_repository import SQLiteMetadataRepository
from sql_pilot_engine.runtime.human_approval import (
    HumanApprovalGate,
    HumanApprovalRecord,
    HumanApprovalRequest,
    HumanApprovalStatus,
)
from sql_pilot_engine.schemas.requests import (
    SQLExplainRequest,
    SQLFixRequest,
    SQLOptimizeRequest,
    SQLReviewRequest,
)
from sql_pilot_engine.spec.models import (
    FixedReportField,
    FixedReportPartition,
    FixedReportSpec,
    FixedReportWriteTarget,
)


class AcceptanceStopped(RuntimeError):
    pass


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be boolean, got {raw!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Agent3.0 production acceptance: real LLM + mandatory Human-in-the-Loop"
        )
    )
    parser.add_argument("--sql", type=Path, required=True, help="User-selected SQL file")
    parser.add_argument("--dialect", default="maxcompute")
    parser.add_argument(
        "--metadata-db",
        type=Path,
        default=None,
        help="Optional authoritative Metadata SQLite DB",
    )
    parser.add_argument(
        "--spec-json",
        type=Path,
        default=None,
        help="Optional FixedReportSpec JSON for Production Generate acceptance",
    )
    parser.add_argument(
        "--optimization-goal",
        action="append",
        default=[],
        help="Optimization goal; may be supplied multiple times",
    )
    parser.add_argument(
        "--use-real-llm",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("AGENT3_USE_REAL_LLM"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Local acceptance artifact directory; defaults under validation_runs/",
    )
    return parser.parse_args()


def _section(title: str) -> None:
    print(f"\n{'=' * 16} {title} {'=' * 16}")


def _build_real_llm() -> tuple[DeepSeekLLMClient, str, str]:
    settings = load_deepseek_settings()
    transport = OpenAICompatibleTransport(settings.provider)
    client = DeepSeekLLMClient(
        transport=transport,
        request_config=settings.structured_request,
    )
    return client, settings.provider.name, settings.provider.model


def _metadata_factory(path: Path | None):
    if path is None:
        return None
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Metadata DB not found: {resolved}")
    return lambda: SQLiteMetadataRepository(resolved)


def _decision(
    *,
    stage: str,
    summary: str,
    candidate_sql: str | None = None,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    machine_gate_passed: bool = True,
) -> HumanApprovalRecord:
    request = HumanApprovalRequest(
        stage=stage,
        summary=summary,
        candidate_sql=candidate_sql,
        trace_id=trace_id,
        metadata=metadata or {},
        machine_gate_passed=machine_gate_passed,
    )

    print("\nHuman-in-the-Loop decision required.")
    if not machine_gate_passed:
        print("Machine gate did NOT pass. Human approval cannot override this block.")
    print("Type exactly APPROVE to approve, REJECT to reject.")
    print("Any other non-empty text is recorded as feedback and stops this run.")
    value = input("Human decision > ")
    record = HumanApprovalGate.decide(request, value)
    print("HITL status:", record.status.value)
    return record


def _require_stage_approval(record: HumanApprovalRecord) -> None:
    if record.status is HumanApprovalStatus.APPROVED:
        return
    raise AcceptanceStopped(
        f"Acceptance stopped at {record.stage}: {record.status.value}"
    )


def _spec_from_json(path: Path) -> FixedReportSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    targets = []
    for target in payload["write_targets"]:
        targets.append(
            FixedReportWriteTarget(
                table_name=target["table_name"],
                fields=tuple(
                    FixedReportField(
                        name=item["name"],
                        business_definition=item.get("business_definition", ""),
                        expression_hint=item.get("expression_hint"),
                    )
                    for item in target["fields"]
                ),
                partitions=tuple(
                    FixedReportPartition(
                        name=item["name"],
                        value=item.get("value"),
                    )
                    for item in target.get("partitions", [])
                ),
            )
        )

    return FixedReportSpec(
        report_name=payload["report_name"],
        business_requirement=payload["business_requirement"],
        source_tables=tuple(payload["source_tables"]),
        write_targets=tuple(targets),
        parameters=tuple(payload.get("parameters", [])),
        session_settings=tuple(
            (item["name"], item["value"])
            for item in payload.get("session_settings", [])
        ),
        constraints=tuple(payload.get("constraints", [])),
    )


def _make_output_dir(path: Path | None) -> Path:
    if path is not None:
        result = path
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        result = Path("validation_runs") / stamp
    result.mkdir(parents=True, exist_ok=False)
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _has_blocking_issue(issues: list[dict[str, Any]]) -> bool:
    return any(bool(item.get("blocking")) for item in issues)


def main() -> None:
    args = parse_args()
    if not args.use_real_llm:
        raise SystemExit(
            "Formal acceptance requires a real LLM. Re-run with --use-real-llm "
            "or AGENT3_USE_REAL_LLM=1."
        )

    sql_path = args.sql.resolve()
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    original_sql = sql_path.read_text(encoding="utf-8")
    if not original_sql.strip():
        raise ValueError("SQL file is empty.")

    output_dir = _make_output_dir(args.output_dir)
    metadata_factory = _metadata_factory(args.metadata_db)
    metadata_provider = metadata_factory() if metadata_factory is not None else None
    llm_client, llm_provider, llm_model = _build_real_llm()
    engine = build_sql_pilot_engine(
        llm_client=llm_client,
        metadata_provider_factory=metadata_factory,
    )

    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input_sql": str(sql_path),
        "dialect": args.dialect,
        "llm": {
            "real_llm_required": True,
            "provider": llm_provider,
            "model": llm_model,
        },
        "metadata_enabled": metadata_factory is not None,
        "human_approval_required": True,
        "stages": {},
        "human_decisions": [],
        "coverage": {
            "program_evidence": False,
            "explain": False,
            "review": False,
            "fix": False,
            "optimize": False,
            "production_generate": False,
        },
        "final_status": "running",
        "human_approved_sql": None,
    }

    current_sql = original_sql

    try:
        _section("0. Program / Evidence")
        evidence = ProgramEvidenceContextBuilder().build(
            current_sql,
            dialect=args.dialect,
            metadata_provider=metadata_provider,
        )
        evidence_payload = evidence.to_prompt_payload(max_lineage_columns=1000)
        report["stages"]["program_evidence"] = evidence_payload
        report["coverage"]["program_evidence"] = True
        _write_json(output_dir / "program_evidence.json", evidence_payload)
        program = evidence_payload["program"]
        print("Statements:", program["statement_count"])
        print("CTEs:", program["cte_count"])
        print("Read tables:", program["read_tables"])
        print("Write targets:", program["write_targets"])
        print("Lineage available:", evidence_payload["lineage"]["available"])

        _section("1. Production Explain · REAL LLM")
        explain = engine.explain(
            SQLExplainRequest(
                sql=current_sql,
                file_path=str(sql_path),
                dialect=args.dialect,
                enable_metadata=metadata_factory is not None,
                enable_llm=True,
                llm_provider=llm_provider,
            )
        )
        report["stages"]["explain"] = explain.to_dict()
        _write_json(output_dir / "explain.json", explain.to_dict())
        if not explain.success:
            raise RuntimeError(explain.error_message or "Explain failed")
        llm_enriched = bool(explain.explain_quality.get("llm_enriched"))
        if not llm_enriched:
            raise RuntimeError(
                "Formal acceptance requires successful LLM Explain enrichment; "
                "the capability fell back to deterministic-only output."
            )
        report["coverage"]["explain"] = True
        print("Summary:", explain.sql_summary)
        print("Business purpose:", explain.business_purpose)
        print("CTE steps:", len(explain.cte_steps))
        print("Uncertainties:", len(explain.uncertainties))
        print("LLM enriched:", llm_enriched)
        explain_approval = _decision(
            stage="explain",
            summary="Confirm that the production explanation matches the SQL semantics.",
            trace_id=explain.trace_id,
            metadata={
                "uncertainty_count": len(explain.uncertainties),
                "llm_enriched": llm_enriched,
            },
        )
        report["human_decisions"].append(explain_approval.to_dict())
        _require_stage_approval(explain_approval)

        _section("2. Trusted SQL Review · REAL LLM")
        review = engine.review(
            SQLReviewRequest(
                sql=current_sql,
                file_path=str(sql_path),
                dialect=args.dialect,
                enable_metadata=metadata_factory is not None,
                enable_llm=True,
                llm_provider=llm_provider,
            )
        )
        report["stages"]["review"] = review.to_dict()
        _write_json(output_dir / "review.json", review.to_dict())
        if not review.success:
            raise RuntimeError(review.error_message or "Review failed")
        report["coverage"]["review"] = True
        print("Risk level:", review.risk_level)
        print("Issue count:", review.issue_count)
        for issue in review.issues:
            print("-", json.dumps(issue, ensure_ascii=False))
        review_approval = _decision(
            stage="review",
            summary="Confirm that the deterministic + LLM review is materially correct.",
            trace_id=review.trace_id,
            metadata={"risk_level": review.risk_level, "issue_count": review.issue_count},
        )
        report["human_decisions"].append(review_approval.to_dict())
        _require_stage_approval(review_approval)

        _section("3. Production Fix · REAL LLM")
        if review.issue_count == 0:
            report["stages"]["fix"] = {
                "status": "not_exercised",
                "reason": "The selected SQL produced no review issues. Use a SQL case with a real fixable issue to validate Fix.",
            }
            print("Fix not exercised: Review returned zero issues.")
        else:
            fix = engine.fix(
                SQLFixRequest(
                    sql=current_sql,
                    file_path=str(sql_path),
                    dialect=args.dialect,
                    enable_metadata=metadata_factory is not None,
                    enable_llm=True,
                    llm_provider=llm_provider,
                    fix_provider="llm",
                ),
                prior_review=review,
            )
            report["stages"]["fix"] = fix.to_dict()
            _write_json(output_dir / "fix.json", fix.to_dict())
            if not fix.success:
                raise RuntimeError(fix.error_message or "Fix failed")
            print("Fix source:", fix.fix_source)
            print("Applied fixes:", fix.applied_fixes)
            print("Manual notes:", fix.manual_notes)
            if fix.fixed_sql and fix.fixed_sql != current_sql:
                (output_dir / "fix_candidate.sql").write_text(
                    fix.fixed_sql, encoding="utf-8"
                )
                re_review = engine.review(
                    SQLReviewRequest(
                        sql=fix.fixed_sql,
                        file_path=str(sql_path),
                        dialect=args.dialect,
                        enable_metadata=metadata_factory is not None,
                        enable_llm=True,
                        llm_provider=llm_provider,
                    )
                )
                critic = engine.critique(
                    review_response=review,
                    fix_response=fix,
                    re_review_response=re_review,
                    trace_id=fix.trace_id,
                )
                report["stages"]["fix_re_review"] = re_review.to_dict()
                report["stages"]["fix_critic"] = critic.to_dict()
                machine_fix_gate = (
                    re_review.success
                    and critic.success
                    and critic.passed
                    and not _has_blocking_issue(re_review.issues)
                )
                print("Re-review issues:", re_review.issue_count)
                print("Critic passed:", critic.passed)
                print("Fix machine gate:", machine_fix_gate)
                fix_approval = _decision(
                    stage="fix_candidate",
                    summary="Approve or reject the LLM-produced Fix candidate.",
                    candidate_sql=fix.fixed_sql,
                    trace_id=fix.trace_id,
                    metadata={
                        "re_review_success": re_review.success,
                        "re_review_issue_count": re_review.issue_count,
                        "critic_passed": critic.passed,
                    },
                    machine_gate_passed=machine_fix_gate,
                )
                report["human_decisions"].append(fix_approval.to_dict())
                if fix_approval.approved:
                    current_sql = fix_approval.human_approved_sql or current_sql
                    report["coverage"]["fix"] = True
                elif fix_approval.status is HumanApprovalStatus.REJECTED:
                    print("Fix candidate rejected; continuing with the previous SQL.")
                    report["coverage"]["fix"] = True
                else:
                    _require_stage_approval(fix_approval)
            else:
                print("No changed Fix candidate was produced; original SQL remains active.")

        _section("4. Production Optimize · REAL LLM")
        optimize = engine.optimize(
            SQLOptimizeRequest(
                sql=current_sql,
                file_path=str(sql_path),
                dialect=args.dialect,
                enable_metadata=metadata_factory is not None,
                enable_llm=True,
                llm_provider=llm_provider,
                optimization_goals=(
                    args.optimization_goal
                    or ["reduce unnecessary data movement and expensive intermediate work"]
                ),
            ),
            explain_response=explain,
        )
        report["stages"]["optimize"] = {
            "success": optimize.success,
            "status": optimize.status,
            "summary": optimize.summary,
            "suggestions": optimize.suggestions,
            "rewrite_reason": optimize.rewrite_reason,
            "assumptions": optimize.assumptions,
            "confidence": optimize.confidence,
            "error_message": optimize.error_message,
        }
        _write_json(output_dir / "optimize.json", report["stages"]["optimize"])
        if not optimize.success:
            raise RuntimeError(optimize.error_message or "Optimize failed")
        report["coverage"]["optimize"] = True
        print("Status:", optimize.status)
        print("Summary:", optimize.summary)
        for item in optimize.suggestions:
            print("-", json.dumps(item, ensure_ascii=False))
        if optimize.candidate_sql and optimize.candidate_sql != current_sql:
            (output_dir / "optimize_candidate.sql").write_text(
                optimize.candidate_sql, encoding="utf-8"
            )
            optimize_machine_gate = (
                optimize.success and optimize.status == "candidate_generated"
            )
            optimize_approval = _decision(
                stage="optimize_candidate",
                summary="Approve or reject the LLM-produced optimization candidate.",
                candidate_sql=optimize.candidate_sql,
                trace_id=optimize.trace_id,
                metadata={"confidence": optimize.confidence},
                machine_gate_passed=optimize_machine_gate,
            )
            report["human_decisions"].append(optimize_approval.to_dict())
            if optimize_approval.approved:
                current_sql = optimize_approval.human_approved_sql or current_sql
            elif optimize_approval.status is HumanApprovalStatus.REJECTED:
                print("Optimization candidate rejected; keeping the previous SQL.")
            else:
                _require_stage_approval(optimize_approval)
        else:
            print("Optimize returned advice only; no SQL rewrite requires approval.")

        _section("5. Production Generate · REAL LLM")
        if args.spec_json is None:
            report["stages"]["production_generate"] = {
                "status": "not_exercised",
                "reason": "Provide --spec-json to validate requirement-to-production-SQL generation.",
            }
            print("Production Generate not exercised: --spec-json was not supplied.")
        else:
            spec = _spec_from_json(args.spec_json.resolve())
            generated = ProductionGenerateService(model=llm_client).generate(
                spec=spec,
                dialect=args.dialect,
                metadata_provider=metadata_provider,
            )
            report["stages"]["production_generate"] = {
                "success": generated.success,
                "trusted_candidate": generated.trusted_candidate,
                "diagnostics": list(generated.diagnostics),
                "review_issues": list(generated.review_issues),
                "validation": generated.validation,
                "evidence_summary": generated.evidence_summary,
            }
            if generated.candidate_sql:
                (output_dir / "generate_candidate.sql").write_text(
                    generated.candidate_sql, encoding="utf-8"
                )
            print("Success:", generated.success)
            print("Machine trusted candidate:", generated.trusted_candidate)
            print("Validation:", json.dumps(generated.validation, ensure_ascii=False))
            if generated.candidate_sql:
                generate_approval = _decision(
                    stage="generate_candidate",
                    summary="Approve or reject the LLM-generated production SQL candidate.",
                    candidate_sql=generated.candidate_sql,
                    metadata={"trusted_candidate": generated.trusted_candidate},
                    machine_gate_passed=generated.trusted_candidate,
                )
                report["human_decisions"].append(generate_approval.to_dict())
                if generate_approval.approved:
                    report["coverage"]["production_generate"] = True
                else:
                    _require_stage_approval(generate_approval)
            else:
                raise RuntimeError("Production Generate did not produce a candidate SQL.")

        _section("6. Final Machine Review · REAL LLM")
        final_review = engine.review(
            SQLReviewRequest(
                sql=current_sql,
                file_path=str(sql_path),
                dialect=args.dialect,
                enable_metadata=metadata_factory is not None,
                enable_llm=True,
                llm_provider=llm_provider,
            )
        )
        report["stages"]["final_review"] = final_review.to_dict()
        _write_json(output_dir / "final_review.json", final_review.to_dict())
        final_machine_gate = (
            final_review.success
            and not _has_blocking_issue(final_review.issues)
        )
        print("Final review success:", final_review.success)
        print("Final blocking issue:", _has_blocking_issue(final_review.issues))

        _section("7. FINAL HUMAN APPROVAL")
        print("Candidate that will become final only after machine gate + human approval:")
        print(current_sql)
        final_approval = _decision(
            stage="final_sql",
            summary="Final production SQL approval. Machine trust is not enough.",
            candidate_sql=current_sql,
            metadata={
                "real_llm": True,
                "provider": llm_provider,
                "model": llm_model,
                "final_review_issue_count": final_review.issue_count,
            },
            machine_gate_passed=final_machine_gate,
        )
        report["human_decisions"].append(final_approval.to_dict())
        _require_stage_approval(final_approval)

        final_sql = final_approval.human_approved_sql
        if final_sql is None:
            raise RuntimeError("Approval contract violation: approved final SQL is missing.")
        report["human_approved_sql"] = final_sql
        report["final_status"] = "human_approved"
        (output_dir / "final_approved.sql").write_text(final_sql, encoding="utf-8")
        print("\nFINAL STATUS: HUMAN_APPROVED")

    except AcceptanceStopped as exc:
        report["final_status"] = "stopped_by_human_or_machine_gate"
        report["error_message"] = str(exc)
        print("\nFINAL STATUS: STOPPED")
        print(exc)
    except Exception as exc:
        report["final_status"] = "failed"
        report["error_message"] = str(exc)
        print("\nFINAL STATUS: FAILED")
        print(exc)
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(output_dir / "acceptance_report.json", report)
        _write_json(output_dir / "human_decisions.json", report["human_decisions"])
        print("Acceptance artifacts:", output_dir.resolve())

    if report["final_status"] != "human_approved":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
