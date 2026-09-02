"""
Context Intelligence 的通用文档与检索结果 Contract。

【架构位置】
Knowledge Source -> ContextDocument -> VectorStore / MandatoryRule -> RetrievedDocument -> QueryContextBuilder

【为什么只定义两类文档】
当前 V1 的 RAG 上下文明确区分：
- BUSINESS_KNOWLEDGE：业务口径、规则、领域知识；
- VERIFIED_SQL：已经人工/系统确认可作为样例的 SQL。

SemanticModel、Physical Metadata 不放进这里，因为它们有自己的结构化 Domain Contract；
把所有知识都塞进通用 Document 会丢失事实类型和治理边界。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ContextDocumentKind(str, Enum):
    """ContextDocument 的稳定知识类型，用于 Retrieval 后按用途过滤结果。"""

    BUSINESS_KNOWLEDGE = "business_knowledge"
    VERIFIED_SQL = "verified_sql"


@dataclass(frozen=True)
class ContextDocument:
    """
    一个可进入 Context Retrieval 的长期知识文档。

    document_id 是稳定身份，用于去重；kind 决定由哪类 Retriever 消费；text 是 Embedding/Prompt
    使用的正文；metadata 只保存检索/追踪所需的轻量标签，不承担新的业务 Domain Model。
    """

    document_id: str
    kind: ContextDocumentKind
    text: str
    metadata: Mapping[str, str]


@dataclass(frozen=True)
class RetrievedDocument:
    """
    一次 Retrieval 的任务级命中结果。

    document 仍指向原 ContextDocument；score 表示本次召回的排序分数。Mandatory Rule 为了复用
    该 Contract 会使用 score=1.0，但那不代表真实向量相似度。
    """

    document: ContextDocument
    score: float
