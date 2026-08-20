from __future__ import annotations

import sqlite3

from pathlib import Path

from sql_pilot_engine.metadata.schema import (
    METADATA_SCHEMA_VERSION,
)

from sql_pilot_engine.standards.models import (
    CanonicalRoot,
    StandardRule,
)


class SQLiteStandardsRepository:
    """
    Standards Runtime 只读 Repository。

    与 Metadata 共用 metadata.db，
    但不共用 Repository Contract。
    """

    def __init__(
        self,
        database_path: str | Path,
    ) -> None:

        self._database_path = Path(
            database_path
        )

    def _connect(
        self,
    ) -> sqlite3.Connection:

        uri = (
            "file:"
            f"{self._database_path.resolve()}"
            "?mode=ro"
        )

        connection = sqlite3.connect(
            uri,
            uri=True,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        try:
            row = connection.execute(
                """
                SELECT schema_version
                FROM metadata_build_info
                WHERE id = 1
                """
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "metadata.db has no "
                    "completed build info."
                )

            if (
                int(row["schema_version"])
                != METADATA_SCHEMA_VERSION
            ):
                raise RuntimeError(
                    "metadata.db schema "
                    "version mismatch."
                )

            return connection

        except Exception:
            connection.close()
            raise

    def get_rule(
        self,
        rule_code: str,
    ) -> StandardRule | None:

        normalized = (
            rule_code
            .strip()
            .upper()
        )

        if not normalized:
            return None

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT
                    rule_code,
                    rule_type,
                    category,
                    rule_text,
                    status,
                    evidence,
                    example,
                    note,
                    source_sheet
                FROM standard_rule
                WHERE rule_code = ?
                LIMIT 1
                """,
                (
                    normalized,
                ),
            ).fetchone()

            if row is None:
                return None

            return self._rule(
                row
            )

    def list_rules(
        self,
        *,
        category: str | None = None,
    ) -> tuple[
        StandardRule,
        ...
    ]:

        with self._connect() as connection:

            if category is None:

                rows = connection.execute(
                    """
                    SELECT
                        rule_code,
                        rule_type,
                        category,
                        rule_text,
                        status,
                        evidence,
                        example,
                        note,
                        source_sheet
                    FROM standard_rule
                    ORDER BY rule_code
                    """
                ).fetchall()

            else:

                rows = connection.execute(
                    """
                    SELECT
                        rule_code,
                        rule_type,
                        category,
                        rule_text,
                        status,
                        evidence,
                        example,
                        note,
                        source_sheet
                    FROM standard_rule
                    WHERE category = ?
                    ORDER BY rule_code
                    """,
                    (
                        category.strip(),
                    ),
                ).fetchall()

            return tuple(
                self._rule(row)
                for row in rows
            )

    def get_canonical_root(
        self,
        chinese_expression: str,
    ) -> CanonicalRoot | None:

        expression = (
            chinese_expression
            .strip()
        )

        if not expression:
            return None

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT
                    canonical_concept,
                    chinese_expression,
                    canonical_root,
                    root_type,
                    status,
                    source,
                    note
                FROM canonical_root
                WHERE
                    chinese_expression = ?
                    AND status = 'CONFIRMED'
                LIMIT 1
                """,
                (
                    expression,
                ),
            ).fetchone()

            if row is None:
                return None

            return CanonicalRoot(
                canonical_concept=(
                    row[
                        "canonical_concept"
                    ]
                ),

                chinese_expression=(
                    row[
                        "chinese_expression"
                    ]
                ),

                canonical_root=(
                    row[
                        "canonical_root"
                    ]
                ),

                root_type=(
                    row[
                        "root_type"
                    ]
                    or ""
                ),

                status=(
                    row["status"]
                ),

                source=(
                    row["source"]
                    or ""
                ),

                note=(
                    row["note"]
                    or ""
                ),
            )

    @staticmethod
    def _rule(
        row: sqlite3.Row,
    ) -> StandardRule:

        return StandardRule(
            rule_code=(
                row[
                    "rule_code"
                ]
            ),

            rule_type=(
                row[
                    "rule_type"
                ]
            ),

            category=(
                row[
                    "category"
                ]
                or ""
            ),

            rule_text=(
                row[
                    "rule_text"
                ]
            ),

            status=(
                row[
                    "status"
                ]
            ),

            evidence=(
                row[
                    "evidence"
                ]
                or ""
            ),

            example=(
                row[
                    "example"
                ]
                or ""
            ),

            note=(
                row[
                    "note"
                ]
                or ""
            ),

            source_sheet=(
                row[
                    "source_sheet"
                ]
                or ""
            ),
        )