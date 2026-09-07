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
    SourceBindingKind,
)
from sql_pilot_engine.program.models import (
    ProgramAnalysisResult,
    SQLProgram,
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

        binding_diagnostics = (
            self
            ._collect_source_binding_diagnostics(
                program
            )
        )

        status = (
            ProgramAnalysisStatus.PARTIAL
            if (
                unsupported_features
                or binding_diagnostics
            )
            else ProgramAnalysisStatus.COMPLETE
        )

        return ProgramAnalysisResult(
            status=status,
            program=program,
            diagnostics=(
                binding_diagnostics
            ),
            unsupported_features=(
                unsupported_features
            ),
        )
        

    @staticmethod
    def _collect_source_binding_diagnostics(
        program: SQLProgram,
    ) -> tuple[
        str,
        ...,
    ]:
        """
        汇总 Program 中显式降级的 Source Binding。

        Resolver 负责保留事实：

            UNRESOLVED

        Service 负责把整体分析状态：

            COMPLETE
                ↓
            PARTIAL

        这样 ScopeResolver 不需要引入另一套 Result DTO，
        ProgramAnalysisService 也不会吞掉真正的内部异常。
        """

        diagnostics: list[
            str
        ] = []

        for scope in (
            program.scope_analyses
        ):
            for binding in (
                scope.source_bindings
            ):
                if (
                    binding.kind
                    is not (
                        SourceBindingKind
                        .UNRESOLVED
                    )
                ):
                    continue

                reason = (
                    binding.unresolved_reason
                    or (
                        "Source binding could "
                        "not be resolved."
                    )
                )

                diagnostics.append(
                    (
                        "Unresolved source binding "
                        f"in {scope.scope_id}: "
                        f"alias='{binding.alias}', "
                        f"reason={reason}"
                    )
                )

        return tuple(
            diagnostics
        )