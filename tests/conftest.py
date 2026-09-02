from __future__ import annotations

import pytest

from runtime_test_factory import (
    build_runtime_graph,
)


@pytest.fixture
def runtime_graph_factory():
    """
    Runtime 测试统一使用正式 Object Graph
    组装方式，避免各测试重新实现
    QueryAgentGraph 的 Composition Root。
    """

    return build_runtime_graph