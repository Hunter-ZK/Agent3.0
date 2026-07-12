# 关键项目决策记录

## 1. 不再继续把 CLI 作为最终产品形态

CLI 只作为调试入口。最终产品应是 Web 应用。

## 2. 当前项目保留为 SQL Review Engine

`sql_review_agent` 不推倒重写，而是作为底层 Engine，被未来 FastAPI / Web UI 调用。

## 3. LLM 要前移为主分析者

未来架构不是“规则主导 + LLM 补充”，而是：

```text
LLM Agent 主导分析
Rules / Metadata / SQL Analysis / RAG 作为工具
```

## 4. Rules 只保留确定性问题

保留少量强确定性规则：

- SELECT *
- DROP / TRUNCATE
- 硬编码日期
- INSERT OVERWRITE TABLE
- 分区表缺 PARTITION
- 表不存在
- 字段不存在
- 全角空格
- allow.fullscan=true
- 明显不完整表达式，后续可加

不要继续写大量语义规则。

## 5. Analysis 降级为轻量摘要器

不再追求完整 SQL Parser。
analysis 只负责给 LLM 提供结构摘要：

- 语句数量
- 是否有 CTE
- 是否有 JOIN
- 是否有 GROUP BY
- 是否有 UNION ALL
- 是否有 INSERT
- 目标表
- 源表列表
- 大致 CTE 名称

## 6. RAG 必须进入项目范畴

JSON mock metadata 只是学习阶段。未来需要：

- 结构化元数据：SQLite / MySQL / DataWorks API
- 文档知识库：Chroma / FAISS / 后续 Milvus 等
- 历史案例库：关系库 + 向量库

## 7. DataAgent 作为架构参考，不直接照搬

借鉴点：

- Web 应用形态
- Agent Workflow
- 向量库知识检索
- 多模型适配
- 工具化架构

不直接照搬 Spring AI Alibaba / Java 全栈，避免复杂度超出当前学习阶段。

## 8. 技术路线选择

近期推荐：

- Python
- FastAPI
- Streamlit
- DeepSeek / Mock LLM
- Chroma 或 FAISS
- SQLite

后续再考虑：

- Vue / React
- Milvus / pgvector / Elasticsearch
- Spring AI Alibaba
- 企业级部署

## 9. 开发方式要求

后续继续遵守：

- 大功能先出设计，再写代码。
- 减少大段网页 Markdown 源码，长文档优先打包源文件。
- 明确新增文件、修改文件、删除文件。
- 只贴必要代码，避免重复劳动。
- 核心代码必须有足够注释，解释属性、参数、使用场景。
- 每阶段保证可运行、可测试。
