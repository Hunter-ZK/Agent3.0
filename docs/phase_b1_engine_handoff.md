# Phase B-1 Engine API 收口交付说明

## 目标

把当前 `ReviewService.review_sql(...)` 的长参数调用收口到统一 Engine 入口，为后续 FastAPI、Streamlit、Agent Workflow 提供稳定边界。

## 新增模块

```text
sql_review_agent/
  engine/
    __init__.py
    sql_review_engine.py
  schemas/
    __init__.py
    requests.py
    responses.py
```

## 核心设计

### Request DTO

- `SQLReviewRequest`：审查请求。
- `SQLFixRequest`：修复请求，继承 `SQLReviewRequest`，额外增加 `fix_provider`。
- `SQLExplainRequest`：C 阶段占位。
- `SQLOptimizeRequest`：C/D 阶段占位。

### Response DTO

- `SQLReviewResponse`：结构化审查响应。
- `SQLFixResponse`：结构化修复响应。

其中 `raw_result` 保留当前 `ReviewResult`，用于兼容已有 `reporting/renderers.py` 与 CLI 输出；后续 Web/API 层应优先使用 `to_dict()` 后的稳定字段。

### Engine

- `SQLReviewEngine.review(request)`：统一审查入口。
- `SQLReviewEngine.fix(request)`：统一修复入口。
- `SQLReviewEngine.explain(request)`：占位，后续接 LLM-first 单 Agent。
- `SQLReviewEngine.optimize(request)`：占位，后续接 LLM/RAG 优化建议。

## 已修改模块

- `sql_review_agent/app/factory.py`
  - 新增 `build_sql_review_engine()`。
- `sql_review_agent/app/cli.py`
  - CLI 改为通过 Engine 调用。
- `sql_review_agent/reviewer.py`
  - 旧函数入口保留，但内部改为走 Engine。
- `pyproject.toml`
  - 增加 `[build-system]`。
  - 增加 `[tool.setuptools.packages.find]`。

## 新增测试

- `tests/test_engine.py`
  - Engine review 响应稳定性。
  - Engine 与 ReviewService 行为等价。
  - Engine fix 字段输出。
  - enable_metadata 自动创建 MockMetadataProvider。
  - 显式 metadata_provider 注入。
  - factory 构建 Engine。

## 验收结果

```bash
python -m pip install -e . --no-deps
python -m pytest -q
```

结果：

```text
30 passed
```

## 下一步

进入 Phase B-2 / B-3：

1. 进一步清理 `ReviewService.review_sql(...)` 长参数，可考虑新增内部参数对象，但不破坏旧调用。
2. 检查 CLI、legacy CLI、reviewer 兼容入口是否还存在重复逻辑。
3. 为 Phase C 设计 `Review/Fix/Explain` 的 LLM-first 单 Agent 契约。
