# 新窗口继续对话提示词

我正在继续一个项目：SQLPilot / SQL Review Agent。

请你先读取我上传的交接包，并以其中内容为准继续。核心背景如下：

1. 我正在学习 AI Agent 开发，目标是做一个面向离线数仓开发、DataWorks / MaxCompute SQL 场景的 AI SQL 优化助手。
2. 我当前 Python 能力还在恢复，曾有 Java 工程基础。希望教学用中文，重要专业词保留英文。
3. 之前已经完成一个 `sql_review_agent` 项目的迁移，包含：
   - core 模型
   - rules 基础规则 / MaxCompute 规则 / Metadata 规则
   - metadata Mock Provider
   - llm Mock / DeepSeek Review / Fixer
   - fixing Auto Fix
   - analysis 轻量 SQL 分析
   - reporting Text / JSON / Markdown
   - services ReviewService
   - app CLI / factory
4. 但我已经认为：继续堆 CLI、正则 parser 和 rule 不符合长期目标。后续应转向 Web + RAG + Agent 架构。
5. 当前代码可以保留为 SQL Review Engine，不再作为最终产品形态。
6. 下一步请从 Phase B 开始：Engine API 收口。目标是新增或调整：
   - `schemas/requests.py`
   - `schemas/responses.py`
   - `engine/sql_review_engine.py`
   - 让 CLI / 未来 FastAPI 都统一调用 Engine，而不是直接依赖 CLI 或 ReviewService 细节。
7. 后续请减少大段网页 Markdown 源码直接回复。涉及长文档或多文件源码时，优先提供文件包或清晰的“文件名 + 修改片段”。
8. 请继续保持：
   - 明确哪些文件新增、哪些修改、哪些删除。
   - 只贴必要代码，避免重复劳动。
   - 对核心代码增加足够注释，解释属性、方法参数、使用场景。
   - 每一步都要先保证可运行、可测试，再继续扩展。

请你先基于交接包，确认当前项目状态，然后开始 Phase B：Engine API 收口方案，不要直接跳到写大量代码。
