# 当前代码状态

## 1. 当前目录角色

当前 `sql_review_agent` 是未来 SQLPilot 的底层 Engine 雏形。

## 2. 当前分层

```text
sql_review_agent/
  app/          CLI 和依赖装配
  core/         核心模型与上下文
  utils/        SQL 文本工具
  analysis/     轻量 SQL 结构摘要
  metadata/     元数据模型和 Mock Provider
  rules/        确定性规则
  llm/          LLM Client / Review / Fix / Prompt / Context
  fixing/       Auto Fix
  reporting/    Text / JSON / Markdown 报告
  services/     ReviewService 主编排
```

## 3. 核心调用链

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

## 4. 已有能力

- Text / JSON / Markdown 输出。
- 基础规则检查。
- MaxCompute / DataWorks 规则。
- Metadata 规则。
- Mock Metadata。
- DeepSeek / Mock LLM Review。
- JSON schema 校验和 Repair。
- Auto Fix。
- LLM Fixer。
- fixed SQL 输出。
- CLI 调试入口。

## 5. 当前问题

- 代码量大，对用户当前 Python 熟练度有压力。
- `analysis` 中正则和文本处理不应成为学习重点。
- 当前效果仍偏基础。
- LLM 还没有成为主导 Agent。
- 缺少 RAG。
- 缺少 Web 产品入口。
- 缺少 Engine API 层，当前 Web 若接入仍会直接依赖 ReviewService 细节。

## 6. 当前最重要文件

P0 重点：

```text
core/models.py
core/context.py
services/review_service.py
llm/clients.py
llm/prompts.py
llm/reviewer.py
llm/fixer.py
```

P1 重点：

```text
metadata/provider.py
rules/registry.py
rules/metadata.py
fixing/auto_fixer.py
```

P2 暂时会用即可：

```text
analysis/parser.py
analysis/analyzer.py
reporting/renderers.py
app/cli.py
```

## 7. 下一步代码方向

不要继续扩展 CLI。
下一步做 Phase B：Engine API 收口。

建议新增：

```text
sql_review_agent/schemas/requests.py
sql_review_agent/schemas/responses.py
sql_review_agent/engine/sql_review_engine.py
```

目标：

```text
CLI / FastAPI / Tests
→ SQLReviewEngine
→ ReviewService
```
