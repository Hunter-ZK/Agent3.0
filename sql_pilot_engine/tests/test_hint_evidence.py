from __future__ import annotations

from sql_pilot_engine.evidence.hints import OptimizerHintEvidenceExtractor
from sql_pilot_engine.program.service import ProgramAnalysisService


def _program(sql: str):
    result = ProgramAnalysisService().analyze(sql)
    assert result.program is not None, result.failure_reason
    return result.program


def test_extracts_mapjoin_name_arguments_and_raw_span():
    sql = """
    SET odps.sql.type.system.odps2 = true;
    SELECT /*+ MAPJOIN(d1, d2) */ f.id
    FROM fact f
    LEFT JOIN dim_one d1 ON f.id = d1.id
    LEFT JOIN dim_two d2 ON f.id = d2.id
    """
    program = _program(sql)
    evidence = OptimizerHintEvidenceExtractor().extract(program)
    assert len(evidence) == 1
    hint = evidence[0]
    assert hint.name == "MAPJOIN"
    assert hint.arguments == ("d1", "d2")
    assert hint.statement_index == 0
    assert sql[hint.span.start.offset : hint.span.end.offset] == "/*+ MAPJOIN(d1, d2) */"


def test_multiple_business_statements_get_distinct_statement_indexes():
    program = _program(
        """
        SELECT /*+ MAPJOIN(d1) */ a.id FROM a LEFT JOIN d1 ON a.id=d1.id;
        SELECT /*+ MAPJOIN(d2) */ b.id FROM b LEFT JOIN d2 ON b.id=d2.id;
        """
    )
    evidence = OptimizerHintEvidenceExtractor().extract(program)
    assert [(item.name, item.arguments, item.statement_index) for item in evidence] == [
        ("MAPJOIN", ("d1",), 0),
        ("MAPJOIN", ("d2",), 1),
    ]


def test_single_scope_statement_can_bind_scope_id():
    program = _program("SELECT /*+ MAPJOIN(d) */ d.id FROM dim_table d")
    evidence = OptimizerHintEvidenceExtractor().extract(program)
    assert len(evidence) == 1
    assert evidence[0].scope_id == "statement:0:root"


def test_multi_scope_statement_does_not_guess_scope_id():
    program = _program(
        """
        WITH base AS (
            SELECT id FROM fact
        ),
        enriched AS (
            SELECT /*+ MAPJOIN(d) */ b.id
            FROM base b
            LEFT JOIN dim_table d ON b.id = d.id
        )
        SELECT id FROM enriched
        """
    )
    evidence = OptimizerHintEvidenceExtractor().extract(program)
    assert len(evidence) == 1
    assert evidence[0].scope_id is None


def test_multiple_hints_in_one_comment_are_preserved():
    program = _program(
        "SELECT /*+ MAPJOIN(d) STREAMTABLE(f) */ f.id FROM fact f LEFT JOIN dim d ON f.id=d.id"
    )
    evidence = OptimizerHintEvidenceExtractor().extract(program)
    assert [(item.name, item.arguments) for item in evidence] == [
        ("MAPJOIN", ("d",)),
        ("STREAMTABLE", ("f",)),
    ]
