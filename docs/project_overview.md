# SQLPilot 项目总览

## 1. 项目定位

SQLPilot 是一个面向离线数仓开发场景的 AI SQL 优化助手。

当前项目从 SQL Review CLI 演进而来，但最终目标不是命令行工具，而是一个 Web 化的 SQL 分析、审查、优化、修复和解释系统。

## 2. 核心目标

- 支持 DataWorks / MaxCompute SQL 场景。
- 支持复杂离线数仓 SQL 的审查和解释。
- 支持 AI 大模型生成优化建议和修复后 SQL。
- 支持接入元数据、开发规范、历史案例和知识库。
- 支持网页交互。

## 3. 当前阶段

当前已完成从单文件脚本到分层工程的迁移，包括：

- 基础规则检查。
- MaxCompute / DataWorks 规则检查。
- Mock 元数据检查。
- 表和字段存在性检查。
- LLM Review。
- DeepSeek / Mock LLM Client。
- 自动生成 fixed SQL。
- Markdown / Text / JSON 报告。
- CLI 调试入口。

## 4. 当前问题

- 代码量偏大。
- 规则和 parser 效果有限。
- LLM 没有成为主分析者。
- Web 使用形态尚未建立。
- 元数据和知识库仍然是 Mock / JSON 形式。
- RAG 尚未引入。

## 5. 项目重新定义

项目后续不再定义为 SQL Review CLI，而定义为：

```text
面向离线数仓开发的 AI SQL Copilot
```

## 6. 使用场景

### SQL Review

输入 SQL，输出风险点、风险等级、原因、建议。

### SQL Optimize

输入复杂 SQL，输出优化后 SQL、优化说明、性能风险和业务逻辑影响。

### SQL Explain

输入历史 SQL，输出分段解释、输入表、输出表、指标口径和业务含义。

### SQL Fix

输入有问题 SQL 或报错，输出修复后 SQL、修改说明和人工确认事项。

### Knowledge QA

基于元数据、规范文档、历史 SQL 回答字段、表、口径和规范问题。

## 7. 当前项目和最终系统关系

当前 `sql_review_agent` 未来应作为 SQL Review / SQL Optimize Engine，被 Web Backend 调用。

未来整体结构：

```text
Web UI
→ Backend API
→ SQLPilot Agent
→ SQL Review Engine
→ Metadata Tool
→ RAG Tool
→ LLM
```

## 8. 后续重点

- Web 交互。
- LLM Agent 编排。
- RAG 知识库。
- 元数据工具化。
- 规则工具化。
- Review / Fix / Explain 多 Agent 协作。

