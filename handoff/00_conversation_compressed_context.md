# 本次长对话压缩上下文

## 1. 用户长期目标

用户希望学习并构建 AI Agent，方向偏向 Agent Engineer。当前重点项目是构建一个面向离线数仓开发场景的 SQL AI 助手。用户工作环境涉及 DataWorks / MaxCompute SQL，日常 SQL 复杂度较高，包含 CTE、UNION ALL、LATERAL VIEW、MAP、GROUPING SETS、多段 INSERT、调度参数、维表关联和复杂业务口径。

用户希望 ChatGPT 作为严格但清晰的 AI Agent 开发导师，中文讲解，保留专业英文词。教学偏好：理论讲解 → 代码演示 → 动手练习 → 检查理解。用户 Python 生疏但有 Java 工程基础，希望代码注释更充分、工程推进更快，但不要过度堆复杂实现。

## 2. 项目早期方向

项目最初名为 `sql-review-agent`，目标是构建一个命令行 SQL Review Agent。早期实现包括：

- 基础规则检查。
- MaxCompute / DataWorks 规则。
- Metadata Provider。
- Mock Metadata JSON。
- LLM Review，支持 Mock / DeepSeek。
- Unified Fixed SQL。
- Markdown 报告。

用户多次要求加快进度，不要太慢。后续进行了大规模重构，从单目录文件堆叠改为分层结构。

## 3. 已完成的 v2.x 迁移

经过迁移，项目形成如下分层：

```text
sql_review_agent/
  app/
  core/
  utils/
  analysis/
  metadata/
  rules/
  llm/
  fixing/
  reporting/
  services/
  cli.py
  reviewer.py
  rule_catalog.py
```

已迁移能力：

- `core`：Severity、Issue、ReviewResult、FixedSqlResult、ReviewContext。
- `rules`：基础规则、MaxCompute / DataWorks 规则、Metadata 规则、RuleRegistry。
- `metadata`：ColumnMetadata、TableMetadata、BaseMetadataProvider、MockMetadataProvider。
- `analysis`：轻量 parser / analyzer，提取 SQL 摘要、CTE、语句数量、目标表、源表、SQL 特征。
- `llm`：DeepSeek / Mock Client、LLMReviewer、LLMFixer、Prompt、JSON Repair、context_builder。
- `fixing`：Auto Fix，生成完整 fixed SQL。
- `reporting`：Text / JSON / Markdown、Review Summary。
- `services`：ReviewService 编排规则、LLM、Fix、上下文。
- `app`：CLI 和 factory。
- 兼容旧入口：`sql_review_agent/cli.py`、`reviewer.py`、`rule_catalog.py`。

## 4. 迁移中遇到的问题

### 4.1 新旧架构混用

出现过 `ImportError: cannot import name 'ALL_RULES' from 'sql_review_agent.rules'`。
原因是旧 `cli.py`、`reviewer.py`、`rule_catalog.py` 仍在引用旧 `rules.py` 的 `ALL_RULES`，但新架构中 `rules` 已变为目录包。
解决方案：旧入口改成兼容壳，转发到新架构。

### 4.2 DeepSeek JSON Schema 问题

DeepSeek 返回合法 JSON，但不一定严格符合本地 schema。例如返回 `description`，缺少 `title/message/evidence/category`。
解决方案：

- Prompt 中强约束输出 JSON 字段。
- 本地严格校验。
- 校验失败时发起一次 JSON Repair 调用。
- Repair 后仍失败才生成 `LLM_REVIEW_FAILED`。

### 4.3 CLI Smoke Test 问题

测试依赖 `examples/sample_refactor.sql`，路径不稳定。
解决方案：测试中使用 `tmp_path` 临时创建 SQL 文件，不依赖 examples。

## 5. 用户后续方向纠偏

用户认为：

1. 当前代码量太大，尤其 analysis 文本处理负担高。
2. 当前效果仍偏基础，不符合“AI 大模型应有更大价值”的预期。
3. LLM 不应只是被 rule 束缚的补充项。
4. 后续要做 Web 代码优化功能，而不是长期命令行工具。
5. 希望借鉴 `spring-ai-alibaba/DataAgent` 的架构，但考虑自身能力有序推进。
6. 向量库 / RAG 应纳入项目范畴，不能长期用 JSON 写死。

最终达成新的方向：

- 当前 `sql_review_agent` 保留为 SQL Review Engine。
- 不继续堆 CLI、复杂 parser 和大量 rules。
- 未来转向 Web + Agent + RAG。
- LLM 应成为主分析者，rules / metadata / analysis / RAG 是工具。

## 6. 新项目定位

项目重新定义为：

```text
SQLPilot：面向离线数仓开发的 AI SQL Copilot
```

目标：在网页中粘贴 SQL，获得：

- SQL Review
- SQL Optimize
- SQL Fix
- SQL Explain
- 风险报告
- 修复后 SQL
- 规范依据 / 元数据依据 / 历史案例依据

## 7. 新阶段规划

后续路线：

1. Phase A：文档化和方向收口。
2. Phase B：Engine API 收口。
3. Phase C：FastAPI Backend。
4. Phase D：Streamlit Web MVP。
5. Phase E：RAG 知识库。
6. Phase F：Agent Workflow。
7. Phase G：工程化升级。

当前用户已说“开始吧”，Phase A 文档化已在对话中给出。由于网页显示 Markdown 源码混乱，用户要求后续长文档直接打包源文件。

## 8. 下一步建议

在新窗口中从 Phase B 开始：Engine API 收口。

目标：让 CLI / 未来 Web / Test 都调用统一 Engine，而不是直接依赖 CLI 或 ReviewService 内部细节。

建议新增：

```text
sql_review_agent/
  schemas/
    requests.py
    responses.py
  engine/
    sql_review_engine.py
```

核心接口：

```python
engine.review(request)
engine.fix(request)
engine.optimize(request)
engine.explain(request)
```

第一步只做 `review` 和 `fix`，不要直接上完整 Web。
