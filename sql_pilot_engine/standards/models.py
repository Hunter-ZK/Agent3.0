from __future__ import annotations

from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class StandardRule:
    rule_code: str
    rule_type: str

    category: str
    rule_text: str
    status: str

    evidence: str = ""
    example: str = ""
    note: str = ""

    source_sheet: str = ""


@dataclass(
    frozen=True,
    slots=True,
)
class CanonicalRoot:
    canonical_concept: str

    chinese_expression: str

    canonical_root: str

    root_type: str

    status: str

    source: str = ""

    note: str = ""