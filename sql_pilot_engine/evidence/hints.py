from __future__ import annotations

import re

from dataclasses import dataclass

from sql_pilot_engine.program.models import (
    SourceSpan,
    SQLProgram,
)


_HINT_COMMENT_PATTERN = re.compile(
    r"/\*\+\s*(?P<body>.*?)\*/",
    re.DOTALL,
)

_HINT_NAME_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*"
)


@dataclass(
    frozen=True,
    slots=True,
)
class OptimizerHintEvidence:
    """
    从 SQLProgram 中确定性提取的一条
    Optimizer Hint Evidence。

    例如：

        /*+ MAPJOIN(dim_org) */

    会得到：

        name = "MAPJOIN"
        arguments = ("dim_org",)
    """

    name: str

    arguments: tuple[
        str,
        ...,
    ]

    statement_index: int

    # 当前只有 statement 唯一 scope 时
    # 才能可靠绑定。
    #
    # 多 CTE / 多 Scope SQL 不猜。
    scope_id: str | None

    # Raw SQL 中真正的位置。
    span: SourceSpan


class OptimizerHintEvidenceExtractor:
    """
    SQLProgram
        ↓
    OptimizerHintEvidence[]

    关键架构边界：

    1. Hint 属于 Evidence，
       不进入 SQLProgram。

    2. 从 program.normalized_sql 提取，
       不使用 statement.normalized_sql。

    3. 使用 SourceMap 映射回 Raw SQL。

    4. 不负责 Hint rewrite / restore。

    5. scope_id 没有足够证据时返回 None，
       不伪造精确 Scope。
    """

    def extract(
        self,
        program: SQLProgram,
    ) -> tuple[
        OptimizerHintEvidence,
        ...,
    ]:

        if (
            program.normalized_sql
            != program.source_map.normalized_text
        ):
            raise ValueError(
                "SQLProgram.normalized_sql and "
                "SourceMap.normalized_text "
                "are inconsistent."
            )

        evidence: list[
            OptimizerHintEvidence
        ] = []

        for comment in (
            _HINT_COMMENT_PATTERN
            .finditer(
                program.normalized_sql
            )
        ):

            # ==============================================
            # normalized position
            #     ↓
            # raw SQL position
            # ==============================================

            raw_span = (
                program
                .source_map
                .normalized_span_to_raw(
                    start=comment.start(),
                    end=comment.end(),
                )
            )

            if raw_span is None:
                raise ValueError(
                    "Optimizer hint could not "
                    "be mapped back to raw SQL."
                )

            # ==============================================
            # Hint 属于哪一条业务 Statement
            # ==============================================

            statement_index = (
                _statement_index_at_offset(
                    program.normalized_sql,
                    comment.start(),
                )
            )

            if (
                statement_index
                >= len(program.statements)
            ):
                raise ValueError(
                    "Optimizer hint statement "
                    "index is inconsistent "
                    "with SQLProgram."
                )

            # ==============================================
            # Scope：
            #
            # 能证明才绑定；
            # 不能证明则 None。
            # ==============================================

            scope_id = _safe_scope_id(
                program,
                statement_index=(
                    statement_index
                ),
            )

            # 一个 Hint comment 里可能有多个 Hint：
            #
            # /*+
            #     MAPJOIN(d)
            #     STREAMTABLE(f)
            # */
            parsed_hints = (
                _parse_hint_body(
                    comment.group(
                        "body"
                    )
                )
            )

            for (
                name,
                arguments,
            ) in parsed_hints:

                evidence.append(
                    OptimizerHintEvidence(
                        name=name,

                        arguments=(
                            arguments
                        ),

                        statement_index=(
                            statement_index
                        ),

                        scope_id=(
                            scope_id
                        ),

                        span=(
                            raw_span
                        ),
                    )
                )

        return tuple(
            evidence
        )


def _safe_scope_id(
    program: SQLProgram,
    *,
    statement_index: int,
) -> str | None:
    """
    只有当前 Statement
    恰好只有一个 Program Scope 时，
    才能可靠绑定 scope_id。

    多 CTE SQL：

        root
        cte:a
        cte:b

    不能仅凭 Hint 位置猜属于哪个 Scope。
    """

    scope_ids = tuple(
        scope.scope_id

        for scope
        in program.scope_analyses

        if (
            scope.statement_index
            == statement_index
        )
    )

    if len(scope_ids) == 1:
        return scope_ids[0]

    return None


def _parse_hint_body(
    body: str,
) -> tuple[
    tuple[
        str,
        tuple[
            str,
            ...,
        ],
    ],
    ...,
]:
    """
    解析：

        MAPJOIN(a,b) STREAMTABLE(c)

    得到：

        (
            ("MAPJOIN", ("a", "b")),
            ("STREAMTABLE", ("c",)),
        )

    注意：
    这里只解析 Hint comment，
    不重新实现 SQL Parser。
    """

    result: list[
        tuple[
            str,
            tuple[
                str,
                ...,
            ],
        ]
    ] = []

    index = 0

    length = len(
        body
    )

    while index < length:

        while (
            index < length
            and (
                body[index].isspace()
                or body[index] == ","
            )
        ):
            index += 1

        if index >= length:
            break

        name_match = (
            _HINT_NAME_PATTERN
            .match(
                body,
                index,
            )
        )

        if name_match is None:
            raise ValueError(
                "Unsupported optimizer "
                "hint syntax near: "
                f"{body[index:]!r}"
            )

        name = (
            name_match
            .group(0)
            .upper()
        )

        index = (
            name_match.end()
        )

        while (
            index < length
            and body[index].isspace()
        ):
            index += 1

        arguments: tuple[
            str,
            ...,
        ] = ()

        if (
            index < length
            and body[index] == "("
        ):

            end = (
                _find_matching_parenthesis(
                    body,
                    index,
                )
            )

            argument_text = (
                body[
                    index + 1:
                    end
                ]
            )

            arguments = (
                _split_arguments(
                    argument_text
                )
            )

            index = end + 1

        result.append(
            (
                name,
                arguments,
            )
        )

    return tuple(
        result
    )


def _find_matching_parenthesis(
    text: str,
    opening_index: int,
) -> int:

    depth = 0

    quote: str | None = None

    index = opening_index

    while index < len(text):

        char = text[index]

        if quote is not None:

            if char == quote:

                if (
                    index + 1
                    < len(text)

                    and (
                        text[
                            index + 1
                        ]
                        == quote
                    )
                ):
                    index += 2
                    continue

                quote = None

            elif (
                char == "\\"
                and (
                    index + 1
                    < len(text)
                )
            ):
                index += 2
                continue

            index += 1

            continue

        if char in {
            "'",
            '"',
            "`",
        }:
            quote = char

        elif char == "(":
            depth += 1

        elif char == ")":

            depth -= 1

            if depth == 0:
                return index

        index += 1

    raise ValueError(
        "Unclosed optimizer "
        "hint argument list."
    )


def _split_arguments(
    text: str,
) -> tuple[
    str,
    ...,
]:

    if not text.strip():
        return ()

    arguments: list[
        str
    ] = []

    start = 0

    depth = 0

    quote: str | None = None

    index = 0

    while index < len(text):

        char = text[index]

        if quote is not None:

            if char == quote:

                if (
                    index + 1
                    < len(text)

                    and (
                        text[
                            index + 1
                        ]
                        == quote
                    )
                ):
                    index += 2
                    continue

                quote = None

            elif (
                char == "\\"
                and (
                    index + 1
                    < len(text)
                )
            ):
                index += 2
                continue

            index += 1

            continue

        if char in {
            "'",
            '"',
            "`",
        }:
            quote = char

        elif char == "(":
            depth += 1

        elif char == ")":
            depth -= 1

        elif (
            char == ","
            and depth == 0
        ):

            argument = (
                text[
                    start:index
                ]
                .strip()
            )

            if argument:
                arguments.append(
                    argument
                )

            start = index + 1

        index += 1

    argument = (
        text[start:]
        .strip()
    )

    if argument:
        arguments.append(
            argument
        )

    return tuple(
        arguments
    )


def _statement_index_at_offset(
    text: str,
    offset: int,
) -> int:
    """
    计算 Hint 所属 Statement。

    只统计字符串和注释之外的
    statement terminator `;`。

    避免：

        'abc;def'

    这样的字符串误切 Statement。
    """

    statement_index = 0

    index = 0

    quote: str | None = None

    while (
        index
        < min(
            offset,
            len(text),
        )
    ):

        char = text[index]

        nxt = (
            text[index + 1]

            if (
                index + 1
                < len(text)
            )

            else ""
        )

        if quote is not None:

            if char == quote:

                if (
                    index + 1
                    < len(text)

                    and (
                        text[
                            index + 1
                        ]
                        == quote
                    )
                ):
                    index += 2
                    continue

                quote = None

            elif (
                char == "\\"
                and (
                    index + 1
                    < len(text)
                )
            ):
                index += 2
                continue

            index += 1

            continue

        if char in {
            "'",
            '"',
            "`",
        }:

            quote = char

            index += 1

            continue

        # ----------------------------------------------
        # -- line comment
        # ----------------------------------------------

        if (
            char == "-"
            and nxt == "-"
        ):

            newline = text.find(
                "\n",
                index + 2,
            )

            if (
                newline < 0
                or newline >= offset
            ):
                break

            index = newline + 1

            continue

        # ----------------------------------------------
        # /* block comment */
        # ----------------------------------------------

        if (
            char == "/"
            and nxt == "*"
        ):

            end = text.find(
                "*/",
                index + 2,
            )

            if (
                end < 0
                or (
                    end + 2
                    > offset
                )
            ):
                break

            index = end + 2

            continue

        if char == ";":
            statement_index += 1

        index += 1

    return statement_index