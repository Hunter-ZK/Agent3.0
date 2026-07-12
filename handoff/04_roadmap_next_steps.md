# 后续路线图

## Phase A：文档化和方向收口

当前交接包即 Phase A 的产物。

目标：

- 压缩上下文。
- 明确项目定位。
- 明确当前代码结构。
- 明确下一阶段方向。

## Phase B：Engine API 收口

目标：把当前 CLI 项目收口为可被 Web 调用的 Engine。

新增建议：

```text
sql_review_agent/
  schemas/
    requests.py
    responses.py
  engine/
    sql_review_engine.py
```

目标接口：

```python
engine.review(request)
engine.fix(request)
engine.optimize(request)
engine.explain(request)
```

第一步只实现 `review` 和 `fix`。

完成标准：

- CLI 可以继续用。
- 未来 FastAPI 可以直接调用 Engine。
- Request / Response 结构稳定。
- 不再让 Web 直接依赖 CLI 或 ReviewService 细节。

## Phase C：FastAPI Backend

目标：提供 Web API。

API 初版：

```text
POST /api/sql/review
POST /api/sql/fix
POST /api/sql/optimize
POST /api/sql/explain
GET  /api/health
```

## Phase D：Streamlit Web MVP

目标：网页粘贴 SQL → 点击分析 → 展示报告和 fixed SQL。

页面结构：

- SQL 输入框。
- 任务类型选择。
- LLM / Metadata / RAG 开关。
- Review Summary。
- Issue 列表。
- Fixed SQL。
- 继续追问区。

## Phase E：RAG 知识库

目标：让 LLM 能检索规范、元数据说明、历史案例。

初版：

- Chroma 或 FAISS。
- 本地 Markdown / txt 文档。
- 基础 embedding。

## Phase F：Agent Workflow

目标：从单次 LLM 调用升级为多步骤 Agent。

流程：

```text
Intent Agent
→ Context Collector
→ Review Agent
→ Fix Agent
→ Critic Agent
→ Report Agent
```

## Phase G：工程化升级

内容：

- 配置文件。
- 日志。
- 会话历史。
- 报告存储。
- 批量 SQL 扫描。
- 用户设置。
- 模型配置。
- 知识库管理。
- CI / Tests。

## 暂缓事项

- 完整 SQL AST Parser。
- 复杂字段血缘。
- 自动连接生产数据库执行。
- 多租户权限。
- 企业级审计。
- 直接照搬 Spring AI Alibaba DataAgent。
- Milvus 集群部署。
- Vue 完整前端工程。

## 最近一步

新窗口应直接进入：

```text
Phase B：Engine API 收口
```
