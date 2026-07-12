# 当前代码结构说明

## 1. 当前项目角色

当前 `sql_review_agent` 是 SQLPilot 的底层 Engine 雏形。

它承担：

- SQL 基础审查。
- 确定性规则检查。
- 元数据辅助检查。
- LLM 语义审查。
- 自动修复。
- 报告生成。
- CLI 调试。

## 2. 当前目录结构

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

## 3. 模块说明

### app

CLI 和依赖装配。未来 CLI 只作为调试入口。

### core

核心模型，包括 Issue、ReviewResult、FixedSqlResult、ReviewContext。

### utils

SQL 文本工具，处理注释、标准化、全角空格等。

### analysis

轻量 SQL 结构摘要，不是完整 SQL Parser。

### metadata

元数据模型和 Provider 抽象。当前是 Mock JSON，后续接 SQLite / DataWorks API。

### rules

确定性规则。未来降级为 Agent 可调用工具。

### llm

LLM Client、Prompt、Reviewer、Fixer、JSON 校验和 Repair、上下文构造。

### fixing

规则确定性自动修复，生成完整 fixed SQL。

### reporting

Text / JSON / Markdown 报告。

### services

ReviewService 主编排入口。

## 4. 当前主调用链

```text
CLI
→ app/factory.py
→ services/review_service.py
→ RuleRegistry.run()
→ build_analysis_context_text()
→ build_metadata_context_text()
→ LLMReviewer.review()
→ generate_fixed_sql()
→ LLMFixer.fix()
→ ReviewResult
→ reporting/renderers.py
```

## 5. 当前应重点理解的文件

P0：

```text
core/models.py
core/context.py
services/review_service.py
llm/clients.py
llm/prompts.py
llm/reviewer.py
llm/fixer.py
```

P1：

```text
metadata/provider.py
rules/registry.py
rules/metadata.py
fixing/auto_fixer.py
```

P2：

```text
analysis/parser.py
analysis/analyzer.py
reporting/renderers.py
app/cli.py
```

## 6. 当前代码未来处理

保留：core、llm、metadata 抽象、少量 rules、fixing 工具。

收缩：analysis 复杂度、CLI 主入口地位、规则数量。

新增：Engine API、FastAPI、Web、RAG、Agent Workflow。

