# SQLPilot 新架构设计

## 1. 新架构目标

从 SQL Review CLI 升级为 Web 化 AI SQL Copilot。

支持：

- Web 粘贴 SQL。
- 一键 Review / Fix / Optimize / Explain。
- 查看风险报告和优化后 SQL。
- 接入元数据、规范文档、历史案例。
- 支持多轮对话式修改。

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

第二阶段：Vue / React。

## 4. 后端路线

第一阶段使用 FastAPI。

API 初版：

```text
POST /api/sql/review
POST /api/sql/fix
POST /api/sql/optimize
POST /api/sql/explain
GET  /api/health
```

## 5. Agent 层

初期：

```text
SQLReviewAgent
SQLOptimizeAgent
SQLExplainAgent
SQLFixAgent
```

后续：

```text
Intent Agent
→ Context Collector
→ Review Agent
→ Fix Agent
→ Critic Agent
→ Report Agent
```

## 6. Tool 层

- SQL Analysis Tool：轻量 SQL 结构摘要。
- Rule Tool：确定性规则。
- Metadata Tool：表、字段、分区、层级。
- RAG Tool：规范、案例、字段说明。
- Auto Fix Tool：确定性修复。
- LLM Tool：模型调用、JSON 输出、Repair。

## 7. Knowledge 层

包括：

- 结构化元数据。
- 文档知识库。
- 历史案例库。

## 8. 技术路线

近期：

- Python。
- FastAPI。
- Streamlit。
- Chroma / FAISS。
- SQLite。

后续：

- Vue / React。
- Milvus / pgvector / Elasticsearch。
- Spring AI Alibaba 可作为参考。

