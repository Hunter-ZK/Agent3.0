# SQLPilot 未来架构

## 1. 总体定位

SQLPilot 是面向离线数仓开发的 AI SQL Copilot。

输入：

- SQL
- 用户目标
- 报错信息，可选
- 元数据，可选
- 规范文档，可选
- 历史案例，可选

输出：

- SQL 审查报告
- 优化建议
- 修复后 SQL
- SQL 解释
- 风险等级
- 人工确认事项
- 依据来源

## 2. 总体架构

```text
Frontend
  ↓
Backend API
  ↓
SQLPilot Agent
  ↓
Tools
  ├── SQL Analysis Tool
  ├── Rule Tool
  ├── Metadata Tool
  ├── RAG Tool
  ├── Auto Fix Tool
  └── LLM Tool
  ↓
Storage / Knowledge
  ├── Metadata Store
  ├── Vector Store
  ├── Review History
  └── Config Store
```

## 3. 前端路线

第一阶段：Streamlit。

原因：

- 快速原型。
- Python 友好。
- 不需要复杂前端工程。

第二阶段：Vue / React。

用于多页面、会话、权限、报告管理等。

## 4. 后端路线

第一阶段使用 FastAPI。

初始 API：

```text
POST /api/sql/review
POST /api/sql/fix
POST /api/sql/optimize
POST /api/sql/explain
GET  /api/health
```

## 5. Agent 路线

初期不要直接上复杂图工作流。先做：

```text
SQLReviewAgent
SQLFixAgent
SQLExplainAgent
SQLOptimizeAgent
```

后续升级为：

```text
Intent Agent
→ Context Collector
→ Review Agent
→ Fix Agent
→ Critic Agent
→ Report Agent
```

## 6. RAG 路线

第一批知识：

- SQL 开发规范
- DataWorks 调度参数规范
- MaxCompute 常见问题
- 字段和表说明
- 历史 SQL 优化案例

第一阶段向量库：

- Chroma 或 FAISS

后续升级：

- Milvus
- pgvector
- Elasticsearch

## 7. Storage 路线

第一阶段：

- 本地文件
- SQLite
- Chroma / FAISS

后续：

- MySQL / PostgreSQL
- Milvus / pgvector
- 对象存储

## 8. DataAgent 的关系

DataAgent 是参考项目，不直接照搬。

借鉴：

- Web 应用形态
- Agent 工作流思想
- 向量库知识检索
- 多模型适配
- 工具化架构

暂缓：

- 直接上 Spring AI Alibaba
- 企业级 Java 全栈
- 图工作流复杂实现
- Milvus 集群部署

## 9. 一句话

未来架构是：

```text
以 LLM Agent 为主导，以规则、元数据、知识库、SQL 分析为工具，通过 Web 页面为数仓开发提供 SQL 审查、解释、优化和修复能力。
```
