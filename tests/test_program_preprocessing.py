from __future__ import annotations

from sql_pilot_engine.program.preprocessing import (
    preprocess_program_sql,
)


def test_plain_sql_is_preserved():
    """
    【测试目标】

    最基本的不变量：

        如果 SQL 根本不需要 Preprocessing，
        就绝不能擅自修改它。

    这是防止 Preprocessor “越权处理”的第一道测试。
    """

    raw_sql = (
        "SELECT id, amount\n"
        "FROM loan_table\n"
        "WHERE status = 1;"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    assert (
        result.normalized_sql
        == raw_sql
    )

    assert (
        result.session_hints
        == ()
    )

    assert (
        result.parameters
        == ()
    )


def test_top_level_set_is_extracted():
    """
    【测试目标】

    SET：

        应该离开 SQLParser 输入

    但：

        不能从 Program 信息中消失。
    """

    raw_sql = (
        "SET engine.option=true;\n"
        "\n"
        "SELECT id\n"
        "FROM loan_table;"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    assert len(
        result.session_hints
    ) == 1

    session_hint = (
        result.session_hints[
            0
        ]
    )

    assert (
        session_hint.name
        == "engine.option"
    )

    assert (
        session_hint.value
        == "true"
    )

    assert (
        session_hint.raw_text
        == "SET engine.option=true;"
    )

    assert (
        result.normalized_sql
        == (
            "SELECT id\n"
            "FROM loan_table;"
        )
    )


def test_set_text_inside_string_is_not_extracted():
    """
    【测试目标】

    SQL 字符串里面出现：

        SET x=1;

    不能被误认为真正的 SET Statement。

    这是为什么 preprocessing 不能简单：

        regex 删除所有 SET
    """

    raw_sql = (
        "SELECT "
        "'SET fake.option=true;' "
        "AS description;"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    assert (
        result.session_hints
        == ()
    )

    assert (
        result.normalized_sql
        == raw_sql
    )


def test_parameter_is_replaced_with_parser_safe_token():
    """
    【测试目标】

    ${biz_date}

    不赋真实值。

    只替换成：

        Analyzer-safe token。

    同时 ParameterOccurrence 必须保存参数名字。
    """

    raw_sql = (
        "SELECT *\n"
        "FROM loan_table\n"
        "WHERE dt='${biz_date}';"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    assert len(
        result.parameters
    ) == 1

    parameter = (
        result.parameters[
            0
        ]
    )

    assert (
        parameter.name
        == "biz_date"
    )

    assert (
        parameter.analyzer_token
        in result.normalized_sql
    )

    assert (
        "${biz_date}"
        not in result.normalized_sql
    )


def test_same_parameter_has_independent_occurrences():
    """
    【测试目标】

    同一个参数出现两次时：

        不是一个 occurrence。

    它们需要两个独立 Analyzer token。

    后面 AST Analysis 才能分别判断：

        occurrence 1 做什么
        occurrence 2 做什么
    """

    raw_sql = (
        "SELECT *\n"
        "FROM loan_table\n"
        "WHERE begin_period='${period}'\n"
        "AND end_period='${period}';"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    assert len(
        result.parameters
    ) == 2

    first = (
        result.parameters[
            0
        ]
    )

    second = (
        result.parameters[
            1
        ]
    )

    assert (
        first.name
        == "period"
    )

    assert (
        second.name
        == "period"
    )

    assert (
        first.analyzer_token
        != second.analyzer_token
    )


def test_parameter_span_maps_back_to_original_placeholder():
    """
    【测试目标】

    这是 SourceMap 当前最关键的测试。

    Analyzer 看到的是：

        __sqlpilot_parameter_000001__

    但 SourceMap 必须能够重新找到：

        ${biz_date}

    如果这个测试失败，
    后面的 Fix 2.0 就没有可靠源码坐标。
    """

    raw_sql = (
        "SELECT *\n"
        "FROM loan_table\n"
        "WHERE dt='${biz_date}';"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    parameter = (
        result.parameters[
            0
        ]
    )

    raw_span = (
        result.source_map
        .normalized_span_to_raw(
            start=(
                parameter
                .normalized_span
                .start
                .offset
            ),
            end=(
                parameter
                .normalized_span
                .end
                .offset
            ),
        )
    )

    assert raw_span is not None

    original_text = raw_sql[
        raw_span.start.offset:
        raw_span.end.offset
    ]

    assert (
        original_text
        == "${biz_date}"
    )


def test_removed_set_has_no_normalized_position():
    """
    【测试目标】

    被移出 Analyzer SQL 的 SET：

        Raw SQL 中存在

    但：

        normalized SQL 中不存在。

    所以 SET 字符的反向映射必须为 None。
    """

    raw_sql = (
        "SET engine.option=true;\n"
        "SELECT 1;"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    set_raw_offset = (
        raw_sql.index(
            "SET"
        )
    )

    assert (
        result.source_map
        .raw_offset_to_normalized(
            set_raw_offset
        )
        is None
    )

    select_raw_offset = (
        raw_sql.index(
            "SELECT"
        )
    )

    # SET 删除后，
    # normalized SQL 以 SELECT 开头。
    assert (
        result.source_map
        .raw_offset_to_normalized(
            select_raw_offset
        )
        == 0
    )


def test_parameter_occurrence_keeps_raw_line_and_column():
    """
    【测试目标】

    ParameterOccurrence 不只是知道参数名字，

    还必须能够准确回答：

        参数原来位于第几行第几列。

    后面的 Explain / Fix 都会依赖这个能力。
    """

    raw_sql = (
        "SELECT *\n"
        "FROM loan_table\n"
        "WHERE dt='${biz_date}';"
    )

    result = (
        preprocess_program_sql(
            raw_sql
        )
    )

    parameter = (
        result.parameters[
            0
        ]
    )

    assert (
        parameter.raw_span.start.line
        == 3
    )

    # 第三行：
    #
    # WHERE dt='${biz_date}';
    #
    # W 是第 1 列。
    #
    # ${biz_date} 的 $ 是第 11 列。
    assert (
        parameter.raw_span.start.column
        == 11
    )