# Agent3.0 / DataAgent

Agent3.0 是面向数仓开发与数据知识工作的 Domain Agent Harness。

项目目标不是构建一个单一 Text-to-SQL 工具，
而是沉淀一套可复用的：

- Shared Agent Runtime
- Context Intelligence
- Metadata / Semantic / Knowledge / Standards
- SQL Analysis & Validation
- Capability Workflow
- Evaluation & Observability

基础设施。

---

## 当前产品边界

Agent3.0 当前负责：

- 自然语言生成高可信 SQL
- SQL 静态分析与验证
- Metadata 驱动的 Grounding
- Semantic Model 驱动的业务映射
- Business Knowledge / Verified SQL 检索
- Clarification / HITL
- 后续 SQL Review & Optimization
- 后续 Knowledge & Asset QA
- 后续数模与命名建议

当前不负责：

- 在生产数据库执行 SQL
- 数据调度执行
- 数据库运维
- 血缘平台实现
- 完整 Skill / Plugin Platform

---

## Capability

### C1. Text-to-SQL

当前最成熟的 Capability。

```text
Question
→ Context
→ Query Planning
→ SQL Generation
→ Validation
→ Trusted SQL