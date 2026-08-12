from __future__ import annotations

import hashlib
import math
import re

from typing import Protocol


class EmbeddingProvider(Protocol):

    @property
    def dimensions(self) -> int:
        ...

    def embed(
        self,
        text: str,
    ) -> list[float]:
        ...


class TokenHashEmbeddingProvider:
    """仅用于本地开发和测试。

    它不是生产级语义Embedding模型。

    作用是让：
    Retriever → Embedding → Qdrant
    整条工程链在不依赖外部API时也能真实运行。
    """

    def __init__(
        self,
        dimensions: int = 128,
    ) -> None:

        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(
        self,
        text: str,
    ) -> list[float]:

        vector = [
            0.0
            for _ in range(
                self._dimensions
            )
        ]

        tokens = self._tokenize(text)

        for token in tokens:
            digest = hashlib.blake2b(
                token.encode("utf-8"),
                digest_size=8,
            ).digest()

            value = int.from_bytes(
                digest,
                "big",
            )

            index = (
                value
                % self._dimensions
            )

            vector[index] += 1.0

        norm = math.sqrt(
            sum(
                item * item
                for item in vector
            )
        )

        if norm == 0:
            return vector

        return [
            item / norm
            for item in vector
        ]

    @staticmethod
    def _tokenize(
        text: str,
    ) -> list[str]:

        ascii_tokens = re.findall(
            r"[A-Za-z0-9_]+",
            text.lower(),
        )

        chinese = "".join(
            re.findall(
                r"[\u4e00-\u9fff]",
                text,
            )
        )

        chinese_tokens = [
            chinese[index:index + 2]
            for index in range(
                max(
                    len(chinese) - 1,
                    0,
                )
            )
        ]

        return [
            *ascii_tokens,
            *chinese_tokens,
        ]