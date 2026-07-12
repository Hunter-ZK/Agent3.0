# SQLPilot / SQL Review Agent Latest Source

这是当前对话整理出的最新可延续开发版源码包。

## 当前定位

当前项目已经从命令行 SQL Review 工具，收口为未来 SQLPilot Web 应用的底层 Engine。

后续方向：

```text
SQLReviewEngine
→ FastAPI Backend
→ Streamlit Web MVP
→ RAG Knowledge Layer
→ Agent Workflow
```

## 当前能力

- 基础 SQL 规则检查
- MaxCompute / DataWorks 规则检查
- Mock 元数据检查
- 表、字段、分区检查
- LLM Review：Mock / DeepSeek
- LLM JSON Schema Repair
- Auto Fix / Unified Fixed SQL
- LLM Fixer
- SQL 轻量分析上下文
- Text / JSON / Markdown 报告
- CLI 调试入口
- 兼容旧入口 `python -m sql_review_agent.cli`

## 安装

```powershell
pip install -e .
```

## 测试

```powershell
python -m pytest -q
```

## CLI 示例

```powershell
python -m sql_review_agent.app.cli examples\sample_refactor.sql --format text
python -m sql_review_agent.app.cli examples\sample_refactor.sql --enable-metadata --fix-sql --format markdown --output reports\review.md
python -m sql_review_agent.app.cli examples\sample_refactor.sql --enable-metadata --enable-llm --llm-provider mock --fix-sql --fix-provider llm --format markdown
```

## DeepSeek 配置

复制 `.env.example` 为 `.env`，填写：

```env
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 下一步

不要继续扩展 CLI。下一阶段建议从：

```text
Phase B：SQLReviewEngine API 收口
```

开始，为 FastAPI / Streamlit Web MVP 做准备。
# Agent3.0
