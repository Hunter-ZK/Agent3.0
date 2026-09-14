from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sql_pilot_engine.app.sql_core_factory import build_sql_pilot_engine
from sql_pilot_engine.config.llm import load_deepseek_settings
from sql_pilot_engine.llm.clients import DeepSeekLLMClient
from sql_pilot_engine.llm.transport import OpenAICompatibleTransport
from sql_pilot_engine.metadata.sqlite_repository import SQLiteMetadataRepository
from sql_pilot_engine.schemas.requests import SQLExplainRequest
from sql_pilot_engine.schemas.responses import SQLExplainResponse


def _read_env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be boolean, got {raw!r}")


def _build_llm_client(*, use_real_llm: bool):
    if not use_real_llm:
        return None
    settings = load_deepseek_settings()
    transport = OpenAICompatibleTransport(settings.provider)
    return DeepSeekLLMClient(
        transport=transport,
        request_config=settings.structured_request,
    )


def _print_section(title: str) -> None:
    print(f"\n{'=' * 10} {title} {'=' * 10}")


def _print_human(response: SQLExplainResponse) -> None:
    _print_section("总体说明")
    print(response.sql_summary or "<无>")
    print("业务目的:", response.business_purpose or "<当前证据不足，未确认>")

    _print_section("Statement")
    for item in response.statement_explanations:
        print(f"[{item['statement_index']}] {item.get('kind', '')}")
        if item.get("purpose"):
            print("  作用:", item["purpose"])
        if item.get("inputs"):
            print("  输入:", ", ".join(item["inputs"]))
        if item.get("processing_flow"):
            print("  流程:")
            for step in item["processing_flow"]:
                print("   -", step)
        if item.get("write_target"):
            print("  写入:", item["write_target"])
        if item.get("partition_behavior"):
            print("  分区:", item["partition_behavior"])
        if item.get("uncertainties"):
            print("  待确认:", "; ".join(item["uncertainties"]))

    _print_section("表角色")
    for item in response.main_tables:
        print(f"- {item['table']} [{item.get('role', '')}]")
        if item.get("description"):
            print("  Metadata:", item["description"])
        if item.get("business_role"):
            print("  业务角色:", item["business_role"])
        if item.get("usage_summary"):
            print("  使用方式:", item["usage_summary"])

    _print_section("CTE 处理链")
    for item in response.cte_steps:
        deps = ", ".join(item.get("dependencies") or []) or "<无 CTE 依赖>"
        sources = ", ".join(item.get("physical_sources") or []) or "<无直接物理表>"
        print(f"- {item['name']} (statement={item['statement_index']})")
        print("  依赖:", deps)
        print("  物理源:", sources)
        if item.get("purpose"):
            print("  作用:", item["purpose"])
        if item.get("processing_logic"):
            print("  处理逻辑:", item["processing_logic"])
        if item.get("business_semantics"):
            print("  业务语义:", item["business_semantics"])
        if item.get("output_semantics"):
            print("  输出语义:", item["output_semantics"])
        if item.get("semantic_uncertainties"):
            print("  待确认:", "; ".join(item["semantic_uncertainties"]))

    _print_section("目标字段 / Lineage")
    if not response.output_columns:
        print("<当前没有可用的目标字段 Lineage；通常需要权威 Metadata>")
    for item in response.output_columns:
        print(f"- {item['target']}")
        print("  SQL 表达式:", item.get("expression_sql"))
        if item.get("derived_upstream"):
            print("  实际上游:", ", ".join(item["derived_upstream"]))
        if item.get("declared_upstream"):
            print("  登记上游:", ", ".join(item["declared_upstream"]))
        if item.get("meaning"):
            print("  字段含义:", item["meaning"])
        if item.get("derivation_summary"):
            print("  推导说明:", item["derivation_summary"])
        print("  Lineage diff:", item.get("lineage_diff"))

    _print_section("关键变换")
    if not response.key_transformations:
        print("<无 LLM 语义增强，或模型未返回关键变换>")
    for item in response.key_transformations:
        print(
            f"- [{item.get('type') or 'unknown'}] "
            f"{item.get('location') or '<unknown>'}: "
            f"{item.get('description') or ''}"
        )
        if item.get("business_impact"):
            print("  影响:", item["business_impact"])

    _print_section("Review 关注点")
    if not response.suspicious_points:
        print("<无>")
    for item in response.suspicious_points:
        print("-", json.dumps(item, ensure_ascii=False))

    _print_section("不确定性")
    if not response.uncertainties:
        print("<无>")
    for item in response.uncertainties:
        print("-", item)

    _print_section("Explain Quality")
    print(json.dumps(response.explain_quality, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent3.0 production SQL Explain local acceptance"
    )
    parser.add_argument("--sql", type=Path, required=True, help="本地 SQL 文件")
    parser.add_argument(
        "--dialect",
        default="maxcompute",
        help="SQL 方言，默认 maxcompute",
    )
    parser.add_argument(
        "--metadata-db",
        type=Path,
        default=None,
        help="可选：本地 metadata.db（必须是当前 schema version）",
    )
    parser.add_argument(
        "--use-real-llm",
        action=argparse.BooleanOptionalAction,
        default=_read_env_bool("AGENT3_USE_REAL_LLM"),
        help="是否使用真实 DeepSeek structured LLM 做语义解释",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出完整 JSON",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sql = args.sql.read_text(encoding="utf-8")
    llm_client = _build_llm_client(use_real_llm=args.use_real_llm)

    metadata_factory = None
    if args.metadata_db is not None:
        metadata_path = args.metadata_db.resolve()
        metadata_factory = lambda: SQLiteMetadataRepository(metadata_path)

    engine = build_sql_pilot_engine(
        llm_client=llm_client,
        metadata_provider_factory=metadata_factory,
    )
    response = engine.explain(
        SQLExplainRequest(
            sql=sql,
            file_path=str(args.sql),
            dialect=args.dialect,
            enable_llm=args.use_real_llm,
            enable_metadata=args.metadata_db is not None,
            llm_provider="deepseek" if args.use_real_llm else "none",
        )
    )

    if args.json:
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human(response)

    if not response.success:
        raise SystemExit(response.error_message or "Production Explain failed")


if __name__ == "__main__":
    main()
