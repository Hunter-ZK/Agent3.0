from __future__ import annotations

import json
from pathlib import Path

import pytest

from sql_pilot_engine.context.semantic.loader import (
    SemanticModelLoader,
)


# 这一组测试锁定的是“Semantic Asset 文件 -> SemanticMetric Contract”的反序列化边界。
# 它不判断业务资产内容是否正确，也不做 Semantic Asset 盘点；只验证 Phase 4.1 Compiler
# 依赖的结构化字段是否被准确加载、标准化，以及复杂指标是否能诚实保持 expression-only。


def _loan_model_path() -> Path:
    """返回仓库内用于结构化指标 Contract 测试的固定贷款语义模型路径。"""

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    return (
        project_root
        / "sql_pilot_engine"
        / "context"
        / "semantic"
        / "loan_model.json"
    )


def test_simple_metric_has_structured_contract() -> None:
    """
    简单指标必须显式提供 Compiler 可消费的 aggregation + source_column。

    这里只验证 Loader/DTO 是否保留资产声明，不重新验证指标业务口径本身。
    """

    model = (
        SemanticModelLoader()
        .load(
            _loan_model_path()
        )
    )

    metric = model.get_metric(
        "tech_loan_balance"
    )

    assert metric is not None
    assert (
        metric.table
        == "ods_hd_100_cldkxx"
    )
    assert (
        metric.aggregation
        == "sum"
    )
    assert (
        metric.source_column
        == "loan_bal_rmb"
    )
    assert metric.fixed_filters == ()


def test_complex_metric_can_remain_expression_only() -> None:
    """
    复杂加权指标可以只保留 expression，不强迫伪造简单 Compiler 结构。

    这条测试保护一个重要 fallback 语义：aggregation/source_column 为 None 是合法状态，
    MetricSQLCompiler 会据此返回 COMPLEX_EXPRESSION，再让 LLM Generator 接管。
    """

    model = (
        SemanticModelLoader()
        .load(
            _loan_model_path()
        )
    )

    metric = model.get_metric(
        "tech_loan_weighted_rate"
    )

    assert metric is not None
    assert metric.aggregation is None
    assert metric.source_column is None
    assert (
        metric.expression
        == (
            "SUM(loan_bal_rmb * rate) "
            "/ SUM(loan_bal_rmb)"
        )
    )


def test_loader_normalizes_simple_metric_fields(
    tmp_path,
) -> None:
    """
    Loader 必须在资产入口统一清理 aggregation/source_column 的格式噪音。

    这条回归测试专门防止 aggregation 只计算了 ``strip().lower()`` 却没有真正写回变量的错误。
    Compiler 自己即使有二次防御，也不应成为 Loader Contract 错误的掩盖层。
    """

    path = tmp_path / "semantic.json"
    path.write_text(
        json.dumps(
            {
                "tables": [],
                "metrics": [
                    {
                        "name": "metric_a",
                        "description": "test",
                        "expression": "SUM(value)",
                        "table": "table_a",
                        "aggregation": " SUM ",
                        "source_column": " value ",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    metric = (
        SemanticModelLoader()
        .load(path)
        .get_metric("metric_a")
    )

    assert metric is not None
    assert metric.aggregation == "sum"
    assert metric.source_column == "value"


def test_loader_rejects_nested_fixed_filter_values(
    tmp_path,
) -> None:
    """
    fixed filter 的 JSON list 只能包含 SemanticScalar，不能夹带 dict/list 等任意结构。

    这保证运行时 DTO 的真实数据与 ``SemanticFilterValue`` 类型声明一致，也避免 Compiler
    在更下游才遇到无法解释的 Python 对象。
    """

    path = tmp_path / "semantic.json"
    path.write_text(
        json.dumps(
            {
                "tables": [],
                "metrics": [
                    {
                        "name": "metric_a",
                        "description": "test",
                        "expression": "SUM(value)",
                        "table": "table_a",
                        "fixed_filters": [
                            {
                                "column": "status",
                                "operator": "in",
                                "value": [
                                    "active",
                                    {"unexpected": "object"},
                                ],
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported semantic filter value item",
    ):
        SemanticModelLoader().load(path)