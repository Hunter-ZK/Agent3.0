from __future__ import annotations

from typing import Protocol


class Capability(Protocol):
    """
    Agent3.0 一个业务能力。

    示例:

    Text-to-SQL

    SQL Review

    Knowledge QA
    """

    name: str


    def execute(
        self,
        request,
    ):
        ...