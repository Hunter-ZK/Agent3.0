from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sql_pilot_engine.app.factory import build_workflow


def read_sql(
    sql_text: str | None,
    file_path: str | None,
) -> tuple[str, str]:
    if sql_text:
        return sql_text, "<command-line>"

    if file_path:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"SQL file does not exist: {path}"
            )

        return path.read_text(encoding="utf-8"), str(path)

    raise ValueError(
        "Either --sql or --file must be provided."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the SQLPilot agent workflow."
    )

    input_group = parser.add_mutually_exclusive_group(
        required=True
    )

    input_group.add_argument(
        "--sql",
        help="SQL text passed directly from the command line.",
    )

    input_group.add_argument(
        "--file",
        help="Path to a SQL file.",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Maximum number of fix retries.",
    )

    args = parser.parse_args()

    try:
        sql, file_path = read_sql(
            sql_text=args.sql,
            file_path=args.file,
        )

        workflow = build_workflow(
            max_retries=args.max_retries,
        )

        result = workflow.run(
            sql=sql,
            file_path=file_path,
        )

        print(
            json.dumps(
                asdict(result),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        return 0 if result.success else 1

    except Exception as error:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(error),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())