# SQLPilot / SQL Review Agent 对话交接包

这个压缩包用于在新对话窗口继续项目，不需要重新解释前面的长对话。

## 建议使用方式

1. 在新窗口上传本压缩包，或复制 `next_chat/START_HERE_PROMPT.md` 的内容作为第一条消息。
2. 说明你已经完成了当前迁移代码，准备进入 Phase B：Engine API 收口。
3. 后续让 ChatGPT 以本交接包为上下文继续带你开发。

## 文件说明

- `next_chat/START_HERE_PROMPT.md`：新窗口第一条消息建议直接使用。
- `00_conversation_compressed_context.md`：本轮长对话压缩上下文。
- `01_project_decisions.md`：关键决策记录。
- `02_current_code_status.md`：当前代码状态和模块说明。
- `03_future_architecture.md`：未来架构方向。
- `04_roadmap_next_steps.md`：后续阶段路线。
- `05_user_preferences.md`：用户偏好与教学约定。
- `docs/`：上一轮建议创建的项目文档源文件，避免网页 Markdown 显示混乱。

## 当前阶段结论

当前迁移阶段已经基本完成，项目应从“继续堆 CLI / rule / parser”转入：

- Phase A：项目文档化和方向收口，已完成本文档包。
- Phase B：Engine API 收口。
- Phase C：FastAPI Backend。
- Phase D：Streamlit Web MVP。
- Phase E：RAG 知识库。
- Phase F：Agent Workflow。

