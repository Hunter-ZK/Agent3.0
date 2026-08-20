# ADR: Shared Agent Platform V1

- Status: Accepted
- Date: 2026-08-20
- Project: Agent3.0 / DataAgent
- Scope: Shared Agent Platform Foundation

---

## 1. Context

Agent3.0 最初从 SQL Review / Trusted SQL 开始，
随后通过 Text-to-SQL Vertical Slice 建立了：

- SQL 静态分析；
- Metadata Validation；
- Trusted SQL；
- Semantic Model；
- Business Knowledge / Verified SQL RAG；
- Query Planning；
- SQL Generation；
- LangGraph Runtime；
- Clarification / HITL；
- Evaluation。

Text-to-SQL 已经证明这些能力可以形成完整闭环。

但 Text-to-SQL 只是第一个 Capability，
不能继续由它定义整个平台形状。

Agent3.0 V1 的目标架构因此从：

Text-to-SQL-centered application

调整为：

Domain Agent Harness for Data Warehouse Development and Knowledge Work

---

## 2. Product Boundary

Agent3.0 是数仓场景下的智能决策、
代码生成与静态验证平台。

Agent3.0：

- 可以生成 SQL；
- 可以 Review SQL；
- 可以生成 Trusted SQL；
- 可以检索数据资产；
- 可以消费业务知识和治理规范；
- 可以进行 Clarification / HITL；
- 可以提供后续数模与命名建议。

Agent3.0 不负责：

- 在生产数据库直接执行 SQL；
- 数据调度执行；
- 物理数据库运维；
- 生产或维护企业治理规范；
- 当前阶段实现血缘存储平台。

---

## 3. Capability Architecture

当前 Capability：

### C1. Text-to-SQL

自然语言：

Question
→ Context
→ Query Planning
→ SQL Generation
→ Validation
→ Trusted SQL

该 Capability 已经成熟，
并作为平台参考实现。

### C2. SQL Review & Optimization

用户直接提交已有 SQL：

SQL
→ AST Analysis
→ Metadata Validation
→ Anti-Pattern Review
→ Standards Validation
→ Optimization Advice / Trusted SQL

当前底层能力部分已存在，
独立 Capability 在 F5 接入。

### C3. Knowledge & Asset QA

两类查询路径：

Metadata / Asset Question
→ MetadataCatalog

Document / Business Question
→ Document RAG

资产查询和文档 RAG 不合并为一个检索系统。

### C4. Warehouse Modeling & Naming

后续 Capability。

依赖：

- Metadata
- Semantic Model
- Standards
- Shared Validation

在 Platform Foundation 与前三个 Capability
稳定前不启动。

---

## 4. Layer Ownership

Agent3.0 使用以下六层 Ownership：

### Layer 1: Shared Agent Runtime

负责：

- Thread / Turn
- LangGraph StateMachine
- Checkpoint
- Clarification / HITL
- Retry Budget
- Runtime Terminal Status
- Intent Dispatch

Runtime 不拥有业务 Planning 和业务 Validation。

### Layer 2: Capability Agent Workflows

每个 Capability 拥有自己的：

- Domain Plan
- Prompt
- Graph Node
- Graph Edge
- Workflow Routing
- Output Contract

Capability 之间禁止互相 import。

### Layer 3: Context Intelligence

负责：

- Context Planning
- Source Selection
- Retrieval
- Ranking
- Grounding
- Compression
- Token Budget
- Context Assembly
- Context Evidence

Context 是 Knowledge Source
针对当前任务的动态投影。

### Layer 4: Shared Data & Knowledge Plane

长期知识源共有四类：

1. Physical Metadata
2. Semantic Model
3. Business & Case Knowledge
4. Standards

Session Context 不属于长期知识源，
而属于 request-scoped Task Context。

### Layer 5: Analysis, Review & Validation

负责共享的确定性分析与验证：

- SQLGlot AST
- Metadata Validation
- Anti-Pattern
- SQL Rewrite
- Naming Validation
- Grain Validation
- Standards Validation

Capability 1 与 Capability 2
共同消费这一层。

Validator 的代码所有权不属于 Capability 2。

### Layer 6: Cross-cutting Infrastructure

包括：

- LLM Adapter
- Evaluation
- Observability
- Prompt Versioning

---

## 5. Harness Principles

### H1. Model and Harness Are Separate

Capability 只声明模型用途，
不依赖具体 Provider。

模型 Provider 与具体 Model
由集中配置与 Composition Root 决定。

### H2. Knowledge Source != Task Context

长期知识资产：

Metadata / Semantic / Knowledge / Standards

与当前任务 Context
必须保持概念和代码边界。

### H3. Runtime State Belongs to Server Runtime

Thread、Checkpoint、Clarification、
HITL 状态属于 Shared Runtime。

未来 Web、IDE、API 或 DataWorks Client
不得各自实现 Agent Loop。

### H4. Tools Are Read-only and Policy Controlled

Agent Tool 只允许读取：

- Metadata
- Standards
- Documents
- Knowledge

Tool 不允许：

- 执行 SQL；
- 写数据库；
- 修改治理数据；
- 触发调度任务。

Tool 调用必须经过确定性的 Policy Gate。

### H5. Static Validation Is Ground Truth

Agent3.0 不以 SQL Execution
作为当前产品闭环的一部分。

因此：

- SQLGlot
- Metadata
- Certified Join
- Standards
- Deterministic Validators

构成当前系统最重要的 Ground Truth。

没有客观反馈时，
禁止无限扩大自主 Agent Loop。

### H6. Agentic Retrieval Is the Main Retrieval Path

Metadata 与 Standards：

Catalog / FTS / deterministic lookup / Tool

Business Knowledge 与 Documents：

Vector Retrieval

Verified SQL：

Vector Retrieval

Vector Store 是索引，
不是 Source of Truth。

---

## 6. Knowledge Sources

### Physical Metadata

Source of Truth:

metadata.db

Runtime:

read-only

Maintenance:

Excel / DataWorks API
→ Importer
→ complete rebuild
→ metadata.db

MetadataProvider：

确定性窄查询。

MetadataCatalog：

资产发现与搜索。

### Semantic Model

Source of Truth:

Git YAML

包含：

- Metrics
- Dimensions
- Grain
- Alias
- Certified Joins

### Business & Case Knowledge

索引：

Qdrant

内容：

- Business Rules
- Verified SQL
- Documents

Vector Store 不承担事实库职责。

### Standards

Source of Truth:

external governance source
→ Importer
→ metadata.db

包含：

- Root Words
- Naming Standards
- Modeling Standards
- Layer Rules

Runtime 只读。

Standards 不进入 Qdrant。

---

## 7. Metadata Rebuild Decision

metadata.db 使用完整重建模式。

不在 Runtime 数据库中维护长期历史 Snapshot。

流程：

External Source
→ Importer
→ build new metadata database
→ validate
→ replace current metadata.db

历史版本由外部治理资产负责。

因此：

- 不引入 schema migration framework；
- 不维护 active batch version system；
- FTS 在重建时一起重建；
- Standards 与 Metadata 采用同样维护模式。

---

## 8. SQLite Physical Separation

必须使用两个数据库：

metadata.db

负责：

- Metadata
- Standards

Runtime read-only。

checkpoints.db

负责：

- LangGraph Checkpoint
- Clarification / HITL State

Runtime read/write。

禁止合并。

原因：

1. SQLite 文件级并发；
2. Metadata 需要完整重建；
3. Metadata 重建不能破坏 Runtime Session；
4. 两者生命周期完全不同。

checkpoints.db 使用 WAL。

---

## 9. Runtime Identity

Runtime 使用三级身份：

Thread
→ Turn
→ Event

Thread：

持续会话。

Turn：

一次 start() 创建的一次 Agent 工作。

Clarification / HITL resume：

属于原 Turn，
不得创建新 turn_id。

Event：

Turn 内部发生的工作事件。

F1 仅冻结 Event Type，
不实现 Event Bus 和 Streaming。

---

## 10. Runtime Terminal Status

统一终态：

PASS
DENY
RETRY
CLARIFY
HITL

### PASS

所有必要静态校验通过。

### DENY

确定性违规。

不消耗 Retry Budget。

典型情况：

- Permission violation
- Tool Policy rejection
- Mandatory rule violation
- 不允许自动修复的治理违规

### RETRY

存在可以通过重新生成或修改解决的问题。

### CLARIFY

业务语义存在歧义，
或缺少 authoritative rule。

### HITL

需要人工审批或判断。

---

## 11. Planning Model

Planning 分成三层。

### Task Planning

Shared Runtime。

负责：

User Intent
→ Capability

### Context Planning

Shared Context Intelligence。

负责：

Task
→ Required Knowledge Sources

### Domain Planning

Capability-specific。

例如：

Text-to-SQL
→ QueryPlan

SQL Review
→ Review Plan

Knowledge QA
→ Knowledge Plan

Warehouse Modeling
→ Warehouse Plan

禁止创建 Universal Domain Plan。

---

## 12. Context Acquisition

Context 有两个并行出口。

### Pipeline Pre-assembly

适合确定性较强的流程：

Text-to-SQL

由 ContextBuilder 预先组装。

### Agent Tools

适合探索型任务：

SQL Review
Knowledge QA

Agent 主动调用底层检索 Tool。

两者必须复用同一底层实现。

禁止：

Pipeline Retrieval
和
Tool Retrieval

分别维护两套逻辑。

---

## 13. Context Budget

Context 分成：

### Hard Constraints

必须完整保留：

- Mandatory Rules
- Exact Metadata
- Metric Definition
- Certified Join
- Mandatory Standards

### Soft References

可以根据 Score 截断：

- Verified SQL
- Background Knowledge
- Related Documents

宽表需要 Schema Pruning。

主键和分区键不得被裁剪。

---

## 14. LLM Routing

模型调用按 Use Case 路由。

例如：

- Intent Routing
- Query Planning
- SQL Generation
- SQL Review
- Semantic Validation
- Knowledge QA

Capability 不持有：

provider
model name
API endpoint

具体 Model 由集中配置决定。

当前 DeepSeek 是 Provider Implementation，
不是平台 Contract。

---

## 15. Validation Ownership

共享校验逻辑全部属于：

Analysis, Review & Validation

而不是某一个 Capability。

因此：

C1 Text-to-SQL
和
C2 SQL Review

可以共同消费：

SQLAnalysisAdapter
MetadataValidator
AntiPatternValidator
StandardsValidator

Capability 之间不得形成依赖。

---

## 16. Deferred Decisions

以下内容当前明确不实现：

- Full Skill Framework
- Plugin Registry
- Generic Hook Lifecycle
- Multi-Agent Architecture
- Lineage Storage
- Production SQL Execution
- Universal Context DTO
- Universal Domain Plan
- ValidationPipeline abstraction

ValidationPipeline
不早于 F6。

只有至少两个真实消费者后
才允许抽象。

---

## 17. Architecture Migration Map

| Current | Final Ownership | Decision | Phase |
|---|---|---|---|
| runtime/query_graph.py | C1 Workflow + Shared Runtime Contract | 保留，后续明确边界 | F5 |
| services/text_to_sql_service.py | C1 Application Facade | 收薄，不再维护第二条主链 | F5 |
| generation/planner.py | C1 Domain Planning | 保留 | F5 |
| generation/sql_generator.py | C1 Generation | 保留 | F5 |
| generation/llm.py | Model-facing Contract | 暂保留，两个以上 Capability 后再评估 | F5/F6 |
| llm/deepseek_client.py | LLM Infrastructure | 保留 Thin Adapter | F1 |
| llm/protocol.py | Legacy LLM Contract | 暂保留，后续收敛 | F5 |
| context/builder.py | Context Intelligence | 渐进收敛 | F4 |
| context/semantic/* | Semantic Model | 迁往声明式 Git YAML Ownership | F3 |
| metadata/provider.py | Physical Metadata | 保留 | F2 |
| metadata/catalog.py | Physical Metadata | 保留 | F2 |
| metadata/models.py Snapshot DTO | Metadata Maintenance Legacy | 删除公共 Snapshot DTO | F2 |
| metadata SQLite Repository | Metadata Persistence | 收敛为 Runtime Read-only | F2 |
| metadata ingestion | Metadata Maintenance | 保留但与 Runtime 分离 | F2 |
| analysis/* | Shared Analysis | 保留并扩展 | F5 |
| rules/* | Shared Validation | 保留，逐步注册化 | F5/F6 |
| workflow/* | Shared Trusted SQL Validation | 保留，后续归第 5 层明确 ownership | F5 |
| evaluation/* | Cross-cutting Evaluation | 保留 | F7 |
| observability/* | Cross-cutting Observability | 保留并增强 | F4 |
| standards/* | Shared Standards | 新建 | F1/F2 |
| lineage/* | Shared Data Plane | 仅留 Protocol | F1 |
| runtime/checkpoint_* | Shared Runtime | Memory + SQLite 实现 | F1 |
| config/llm_routing.py | Cross-cutting LLM Config | 新建 | F1 |

---

## 18. Dependency Rule

核心分层原则：

> 下层不感知上层。

新模块如果必须知道
“哪个 Capability 在调用我”，
说明它不属于 Shared Layer。

Capability 之间禁止互相 import。

---

## 19. Change Governance

以下变更必须先完成技术讨论：

- Shared Module 新增；
- Runtime 主链修改；
- Knowledge Source 新增；
- Persistence 变化；
- Shared DTO 大改；
- Capability Dependency 变化；
- Validation Lifecycle 大改。

流程：

Problem
→ Requirements
→ Alternatives
→ Trade-off
→ Decision
→ Implementation

禁止边实现边重新定义架构。

---

## 20. Roadmap

F1
Architecture Foundation

F2
Metadata Finalization + Standards

F3
Semantic Model YAML

F4
Context Intelligence Platform

F5
Capability Expansion + ODPS

F6
Validation Pipeline

F7
Full Regression Gate

Warehouse Modeling
在前三个 Capability 稳定后开始。

Lineage
暂缓。

Skill Platform
暂缓。

---

## 21. Decision

本 ADR 自接受之日起，
作为 Agent3.0 Shared Agent Platform V1
的架构基线。

实现优先级：

1. Static Validation Ground Truth
2. Shared Knowledge Correctness
3. Runtime Reliability
4. Context Quality
5. Capability Expansion
6. Framework Generalization

不得为了目录整洁、
通用化或形式上的平台完整性
提前引入没有真实消费者的抽象。