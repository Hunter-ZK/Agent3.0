import subprocess
import sys
from pathlib import Path


def create_sample_sql(tmp_path: Path) -> Path:
    sql_file = tmp_path / "sample_refactor.sql"
    sql_file.write_text("select * from dwd_user_order_detail where dt = '20260601';", encoding="utf-8")
    return sql_file


def test_new_cli_should_run(tmp_path: Path):
    sql_file = create_sample_sql(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-m", "sql_review_agent.app.cli", str(sql_file), "--format", "text"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert "问题总数" in completed.stdout


def test_legacy_cli_should_run(tmp_path: Path):
    sql_file = create_sample_sql(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-m", "sql_review_agent.cli", str(sql_file), "--format", "text"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert "问题总数" in completed.stdout
