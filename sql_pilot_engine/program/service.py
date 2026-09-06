from __future__ import annotations

from sql_pilot_engine.analysis.sql_parser import (
    SQLParser,
)
from sql_pilot_engine.program.builder import (
    ProgramBuilder,
)
from sql_pilot_engine.program.cte_dependencies import (
    CTEDependencyResolver,
)
from sql_pilot_engine.program.enums import (
    ProgramAnalysisStatus,
)
from sql_pilot_engine.program.models import (
    ProgramAnalysisResult,
)
from sql_pilot_engine.program.preprocessing import (
    preprocess_program_sql,
)
from sql_pilot_engine.program.scope_resolver import (
    ScopeResolver,
)


class ProgramAnalysisService:
    """
    SQL Program Analysis 的统一入口。

    【调用链】

        Raw SQL
            ↓
        Preprocess
            ↓
        Parse
            ↓
        ProgramBuilder
            ↓
        ScopeResolver
            ↓
        CTEDependencyResolver
            ↓
        ProgramAnalysisResult

    本 Service 只负责 Program Analysis 编排。

    不负责：
    - Metadata Validation；
    - Review；
    - Fix；
    - Lineage；
    - Execution；
    - Generate。
    """

    def __init__(
        self,
        *,
        parser: SQLParser | None = None,
        builder: ProgramBuilder | None = None,
        scope_resolver: ScopeResolver | None = None,
        dependency_resolver: (
            CTEDependencyResolver | None
        ) = None,
    ) -> None:
        self._parser = (
            parser
            or SQLParser()
        )

        self._builder = (
            builder
            or ProgramBuilder()
        )

        self._scope_resolver = (
            scope_resolver
            or ScopeResolver()
        )

        self._dependency_resolver = (
            dependency_resolver
            or CTEDependencyResolver()
        )

    def analyze(
        self,
        raw_sql: str,
        *,
        dialect: str = "maxcompute",
    ) -> ProgramAnalysisResult:
        """
        分析一份完整 SQL Program。

        Parser failure 属于正常分析结果：
            返回 FAILED。

        Builder / Scope / Dependency 如果出现内部异常：
            直接抛出。

        原因是内部程序错误不能伪装成
        “用户 SQL 分析失败”。
        """

        if not raw_sql.strip():
            return ProgramAnalysisResult(
                status=(
                    ProgramAnalysisStatus.FAILED
                ),
                program=None,
                failure_reason=(
                    "SQL program cannot be empty."
                ),
            )

        preprocess_result = (
            preprocess_program_sql(
                raw_sql
            )
        )

        if not (
            preprocess_result
            .normalized_sql
            .strip()
        ):
            return ProgramAnalysisResult(
                status=(
                    ProgramAnalysisStatus.FAILED
                ),
                program=None,
                failure_reason=(
                    "No analyzable SQL statements "
                    "remain after preprocessing."
                ),
            )

        parse_result = (
            self._parser.parse(
                preprocess_result
                .normalized_sql,
                dialect=dialect,
            )
        )

        if not parse_result.success:
            return ProgramAnalysisResult(
                status=(
                    ProgramAnalysisStatus.FAILED
                ),
                program=None,
                diagnostics=(
                    (
                        parse_result
                        .error_message,
                    )
                    if (
                        parse_result
                        .error_message
                    )
                    else ()
                ),
                unsupported_features=tuple(
                    parse_result
                    .unsupported_features
                ),
                failure_reason=(
                    parse_result
                    .error_message
                    or "SQL parsing failed."
                ),
            )

        program = (
            self._builder.build(
                preprocess_result=(
                    preprocess_result
                ),
                parse_result=(
                    parse_result
                ),
            )
        )

        program = (
            self._scope_resolver.resolve(
                program=program,
                parse_result=(
                    parse_result
                ),
            )
        )

        program = (
            self
            ._dependency_resolver
            .resolve(
                program=program,
                parse_result=(
                    parse_result
                ),
            )
        )

        unsupported_features = tuple(
            parse_result
            .unsupported_features
        )

        status = (
            ProgramAnalysisStatus.PARTIAL
            if unsupported_features
            else ProgramAnalysisStatus.COMPLETE
        )

        return ProgramAnalysisResult(
            status=status,
            program=program,
            unsupported_features=(
                unsupported_features
            ),
        )