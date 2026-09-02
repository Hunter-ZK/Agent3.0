"""
Context Retrieval 使用的 Embedding 抽象与本地确定性替身。

【架构位置】
ContextDocument / User Question
    -> EmbeddingProvider
    -> VectorStore(Qdrant)
    -> RetrievedDocument
    -> KnowledgeRetriever / VerifiedSQLRetriever

【为什么使用 Protocol】
Retrieval 只需要“文本 -> 定长向量”这个能力，不应该依赖 DeepSeek、OpenAI 或某个具体 SDK。
Protocol 允许生产环境替换真实 Embedding Provider，同时让本地测试使用无网络的确定性实现。

【重要边界】
TokenHashEmbeddingProvider 不是语义模型，不应拿它评估生产召回质量。它只保证工程链可运行、结果可复现。
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    """所有 Embedding 实现必须满足的最小结构化接口。"""

    @property
    def dimensions(self) -> int:
        """返回固定向量维度；VectorStore 创建 collection 时必须与它保持一致。"""
        ...

    def embed(
        self,
        text: str,
    ) -> list[float]:
        """把输入文本转换为一个长度等于 dimensions 的浮点向量。"""
        ...


class TokenHashEmbeddingProvider:
    """
    仅用于本地开发和测试的确定性 Token Hash Embedding。

    它通过 Token 哈希落桶 + L2 归一化生成向量，不理解真正的业务语义。这样做的价值是：
    - 无需外部 API / Key；
    - 同一文本每次得到同一向量，测试稳定；
    - Qdrant collection、upsert、search 的真实工程路径仍能被验证。
    """

    def __init__(
        self,
        dimensions: int = 128,
    ) -> None:
        # 保留调用方传入的维度配置；本类不额外施加业务校验，维度合法性由实际 VectorStore 使用方处理。
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        """暴露 VectorStore 建表所需的固定向量长度。"""
        return self._dimensions

    def embed(
        self,
        text: str,
    ) -> list[float]:
        """
        将文本转换为可用于余弦相似度检索的归一化哈希向量。

        流程：tokenize -> BLAKE2b 稳定哈希 -> 维度取模落桶 -> 计数 -> L2 Normalize。
        这里不用 Python 内置 hash()，因为它跨进程默认带随机种子，不适合可复现测试。
        """

        vector = [0.0 for _ in range(self._dimensions)]
        tokens = self._tokenize(text)

        for token in tokens:
            # 固定 digest_size 足以用于桶索引；不承担密码学认证用途。
            digest = hashlib.blake2b(
                token.encode("utf-8"),
                digest_size=8,
            ).digest()
            value = int.from_bytes(digest, "big")
            index = value % self._dimensions
            vector[index] += 1.0

        # L2 归一化使 Qdrant COSINE 比较不会被文本长度简单支配。
        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0:
            # 空文本/无 token 时保持全零向量，避免除零。
            return vector

        return [item / norm for item in vector]

    @staticmethod
    def _tokenize(
        text: str,
    ) -> list[str]:
        """
        生成最小本地 Token 集：ASCII 单词/数字/下划线 + 中文连续文本的二元字符片段。

        这不是生产分词器。二元中文片段只是让相邻汉字获得一些局部重叠，方便工程测试中的简单召回。
        """

        ascii_tokens = re.findall(
            r"[A-Za-z0-9_]+",
            text.lower(),
        )

        chinese = "".join(
            re.findall(r"[\u4e00-\u9fff]", text)
        )
        chinese_tokens = [
            chinese[index:index + 2]
            for index in range(max(len(chinese) - 1, 0))
        ]

        return [*ascii_tokens, *chinese_tokens]
