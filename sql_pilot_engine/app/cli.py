# sql_review_agent/app/cli.py

import argparse
from pathlib import Path

from sql_pilot_engine.app.factory import build_sql_review_engine
from sql_pilot_engine.schemas import SQLFixRequest, SQLReviewRequest
from sql_pilot_engine.reporting.renderers import render_json, render_markdown, render_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQL Review Agent for MaxCompute / DataWorks")
    parser.add_argument("sql_file", help="需要审查的 SQL 文件路径。")
    parser.add_argument("--format", choices=["json", "text", "markdown"], default="text", help="输出格式。")
    parser.add_argument("--output", default=None, help="审查报告输出路径。不传则打印到控制台。")
    parser.add_argument("--mode", choices=["debug", "prod", "backfill"], default="prod", help="运行模式。")
    parser.add_argument("--category", action="append", default=None, help="只运行指定分类规则，可重复传入。")
    parser.add_argument("--enable-metadata", action="store_true", help="启用 Mock 元数据检查。")
    parser.add_argument("--enable-llm", action="store_true", help="启用 LLM 语义审查。")
    parser.add_argument("--llm-provider", choices=["mock", "deepseek"], default="mock", help="LLM Provider。")
    parser.add_argument("--fix-sql", action="store_true", help="生成完整修复后的 SQL，但不覆盖原文件。")
    parser.add_argument("--fix-provider", choices=["auto", "llm"], default="auto", help="SQL 修复方式。")
    parser.add_argument("--fixed-output", default=None, help="修复后 SQL 输出路径。")
    return parser.parse_args()


def read_sql_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"SQL 文件不存在：{path}")
    if not path.is_file():
        raise ValueError(f"路径不是文件：{path}")
    return path.read_text(encoding="utf-8")


def render_result_by_format(format_name: str, result) -> str:
    if format_name == "json":
        return render_json(result)
    if format_name == "markdown":
        return render_markdown(result)
    return render_text(result)


def write_text_file(path: Path, content: str) -> None:
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    sql_path = Path(args.sql_file)
    sql = read_sql_file(sql_path)
    categories = set(args.category) if args.category else None

    need_llm_client = args.enable_llm or (args.fix_sql and args.fix_provider == "llm")
    engine = build_sql_review_engine(enable_llm=need_llm_client, llm_provider=args.llm_provider)

    if args.fix_sql:
        request = SQLFixRequest(
            sql=sql,
            file_path=str(sql_path),
            mode=args.mode,
            categories=categories,
            enable_metadata=args.enable_metadata,
            enable_llm=args.enable_llm,
            llm_provider=args.llm_provider,
            fix_provider=args.fix_provider,
        )
        response = engine.fix(request)
    else:
        request = SQLReviewRequest(
            sql=sql,
            file_path=str(sql_path),
            mode=args.mode,
            categories=categories,
            enable_metadata=args.enable_metadata,
            enable_llm=args.enable_llm,
            llm_provider=args.llm_provider,
        )
        response = engine.review(request)

    if not response.success or response.raw_result is None:
        raise RuntimeError(response.error_message or "SQL Review Engine 执行失败。")

    result = response.raw_result
    rendered_result = render_result_by_format(format_name=args.format, result=result)
    if args.output:
        output_path = Path(args.output)
        write_text_file(output_path, rendered_result)
        print(f"审查报告已写入：{output_path}")
    else:
        print(rendered_result)

    if args.fix_sql and result.fixed_sql_result is not None:
        fixed_output = args.fixed_output or str(sql_path.with_suffix(".fixed.sql"))
        fixed_path = Path(fixed_output)
        write_text_file(fixed_path, result.fixed_sql_result.fixed_sql)
        print(f"修复后 SQL 已写入：{fixed_path}")


if __name__ == "__main__":
    main()
