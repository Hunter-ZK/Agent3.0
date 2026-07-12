# SQLPilot 后续路线图

## Phase A：文档化和方向收口

当前交接包即 Phase A 产物。

## Phase B：Engine API 收口

目标：把当前 CLI 项目收口为可被 Web 调用的 Engine。

计划新增：

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

## Phase C：FastAPI Backend

提供 Web API。

```text
POST /api/sql/review
POST /api/sql/fix
POST /api/sql/optimize
POST /api/sql/explain
GET  /api/health
```

## Phase D：Streamlit Web MVP

网页粘贴 SQL → 点击分析 → 展示报告和 fixed SQL。

## Phase E：RAG 知识库

引入规范、元数据说明、历史案例检索。

初版使用 Chroma 或 FAISS。

## Phase F：Agent Workflow

升级为：

```text
Intent Agent
→ Context Collector
→ Review Agent
→ Fix Agent
→ Critic Agent
→ Report Agent
```

## Phase G：工程化升级

包括配置、日志、会话历史、报告存储、批量扫描、模型配置、知识库管理、CI 等。

## 暂缓事项

- 完整 SQL AST Parser。
- 复杂字段血缘。
- 自动连接生产数据库执行。
- 多租户权限。
- 企业级审计。
- 直接照搬 Spring AI Alibaba DataAgent。
- Milvus 集群部署。
- Vue 完整前端工程。

