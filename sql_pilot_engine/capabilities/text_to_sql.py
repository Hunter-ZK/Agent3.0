from __future__ import annotations

from uuid import uuid4

from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)
from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLCompilationEvidence,
    TextToSQLRequest,
    TextToSQLResponse,
    TextToSQLResult,
    TextToSQLValidationIssue,
)


class TextToSQLCapability:
    """
    Text-to-SQL 的 Application Facade。

    【架构位置】

        Application Caller
            ↓
        TextToSQLCapability              <- 本类
            ↓
        QueryAgentGraph
            ↓
        QueryRuntimeNodes
            ↓
        TextToSQLStageService / domain capabilities

    Capability 只负责三件事：
    1. 接收稳定的 Application Request；
    2. start / resume Runtime；
    3. 把内部 Graph State 投影为稳定 Application Response。

    它不实现 Context Retrieval、Planning、Schema Linking、Metric Compilation、LLM Generation、
    SQL Trust、Semantic Validation、Retry 或 Clarification Routing。否则 Application Facade 会
    再次变成第二套 Workflow。

    Phase 4.1 新增的 Compiler 状态也必须在这里“投影”，而不是把内部 CompilationEvidence
    对象直接暴露给调用方。这保持了 Runtime State != Application DTO 的边界。
    """

    def __init__(
        self,
        *,
        graph: QueryAgentGraph,
    ) -> None:
        # Graph 已由 Composition Root 完整组装；Capability 不创建任何业务依赖。
        self._graph = graph

    # ========================================================
    # Public API
    # ========================================================

    def generate(
        self,
        request: TextToSQLRequest,
    ) -> TextToSQLResponse:
        """
        开启一个新的 Text-to-SQL turn。

        每次 generate() 生成独立 thread_id，供 LangGraph checkpoint 使用。如果流程中断并
        返回 TextToSQLClarification，调用方必须保存响应中的 thread_id，再通过 resume() 继续。
        """

        thread_id = uuid4().hex

        state = self._graph.start(
            thread_id=thread_id,
            question=request.question,
            dialect=request.dialect,
            session_context=request.session_context,
        )

        return self._state_to_response(
            state=state,
            question=request.question,
            thread_id=thread_id,
        )

    def resume(
        self,
        *,
        thread_id: str,
        answer: str,
    ) -> TextToSQLResponse:
        """
        从 Clarification / HITL 恢复原有 Runtime Thread。

        注意：这里不是重新调用 generate()。重新 generate 会创建新 thread/checkpoint，丢失
        前一轮 Runtime 上下文；resume() 必须让 LangGraph 从 interrupt 点继续执行。
        """

        normalized_thread_id = thread_id.strip()
        normalized_answer = answer.strip()

        if not normalized_thread_id:
            raise ValueError(
                "thread_id cannot be empty"
            )

        if not normalized_answer:
            raise ValueError(
                "answer cannot be empty"
            )

        state = self._graph.resume(
            thread_id=normalized_thread_id,
            answer=normalized_answer,
        )

        # 原问题属于 Runtime State 的持久事实。resume 后如果丢失，说明 checkpoint/state contract
        # 已经破坏，不能悄悄用空字符串生成 Application Response。
        question = str(
            state.get(
                "question",
                "",
            )
            or ""
        ).strip()

        if not question:
            raise RuntimeError(
                "Runtime resumed without the original question."
            )

        return self._state_to_response(
            state=state,
            question=question,
            thread_id=normalized_thread_id,
        )

    # ========================================================
    # Application Boundary Mapping
    # ========================================================

    @classmethod
    def _state_to_response(
        cls,
        *,
        state: dict,
        question: str,
        thread_id: str,
    ) -> TextToSQLResponse:
        """
        把内部 LangGraph State 转成稳定 Application DTO。

        这里只允许做“数据形态转换”，不允许根据字段重新推断业务路由。例如不能因为
        compilation_fallback_reason 非空就在这里判失败；fallback 是否继续由 Graph 决定。
        """

        interrupts = state.get(
            "__interrupt__"
        )

        # ====================================================
        # 1. Clarification / HITL Projection
        # ====================================================

        if interrupts:
            # LangGraph 的 interrupt 包装对象属于 Runtime 细节，Application 只暴露其中稳定 payload。
            payload = getattr(
                interrupts[0],
                "value",
                None,
            )

            if not isinstance(payload, dict):
                raise RuntimeError(
                    "Invalid LangGraph interrupt payload."
                )

            clarification_question = str(
                payload.get(
                    "question",
                    "",
                )
                or ""
            ).strip()

            if not clarification_question:
                raise RuntimeError(
                    "Clarification question is missing."
                )

            return TextToSQLClarification(
                question=question,
                clarification_question=clarification_question,
                thread_id=thread_id,
                missing_context=tuple(
                    payload.get(
                        "missing_context",
                        (),
                    )
                    or ()
                ),
                reason=str(
                    payload.get(
                        "reason",
                        "",
                    )
                    or ""
                ),
            )

        # ====================================================
        # 2. Final Result Projection
        # ====================================================

        query_plan = state.get(
            "query_plan"
        )

        # 一个正常结束的非-clarification turn 至少应该已经完成 Planning。
        # 如果既没有 interrupt 又没有 QueryPlan，属于 Runtime Contract 破坏而不是业务失败。
        if query_plan is None:
            raise RuntimeError(
                "Text-to-SQL Runtime finished without QueryPlan or clarification."
            )

        return TextToSQLResult(
            question=question,
            query_plan=query_plan,
            generated_sql=str(
                state.get(
                    "generated_sql",
                    "",
                )
                or ""
            ),
            trusted_sql=state.get(
                "trusted_sql"
            ),
            success=bool(
                state.get(
                    "success",
                    False,
                )
            ),

            # Phase 4.1 observability：这三个标量可以直接稳定投影。
            generation_source=state.get(
                "generation_source"
            ),
            compilation_status=state.get(
                "compilation_status"
            ),
            compilation_fallback_reason=state.get(
                "compilation_fallback_reason"
            ),

            # CompilationEvidence 是内部 domain DTO，必须显式转换为 Application DTO。
            compilation_evidence=cls._compilation_evidence(
                state.get(
                    "compilation_evidence"
                )
            ),

            linking_failures=tuple(
                state.get(
                    "linking_failures",
                    (),
                )
                or ()
            ),
            linking_error_message=state.get(
                "linking_error_message"
            ),
            validation_status=cls._status_text(
                state.get(
                    "validation_status"
                )
            ),
            validation_error_message=state.get(
                "validation_error_message"
            ),

            # 内部 Issue dict 逐项转换为公开 DTO，避免 Review 模型向外泄漏。
            validation_issues=tuple(
                cls._validation_issue_from_raw(item)
                for item in (
                    state.get(
                        "validation_issues",
                        (),
                    )
                    or ()
                )
            ),
            semantic_validation_status=cls._optional_status_text(
                state.get(
                    "semantic_validation_status"
                )
            ),
            semantic_missing_requirements=tuple(
                state.get(
                    "semantic_missing_requirements",
                    (),
                )
                or ()
            ),
            semantic_issues=tuple(
                state.get(
                    "semantic_issues",
                    (),
                )
                or ()
            ),
        )

    @staticmethod
    def _status_text(
        value,
    ) -> str:
        """
        把 Enum / str / None 统一投影成公开字符串状态。

        Runtime 内部有些状态来自 Enum，有些来自 Workflow 的字符串 Contract。Application
        Response 不应该要求调用方识别内部枚举类型，因此在边界统一转换。
        """

        if value is None:
            return "not_run"

        enum_value = getattr(
            value,
            "value",
            None,
        )

        if enum_value is not None:
            return str(enum_value)

        return str(value)

    @classmethod
    def _optional_status_text(
        cls,
        value,
    ) -> str | None:
        """与 _status_text 相同，但保留 None，用于真正可选、尚未执行的阶段状态。"""

        if value is None:
            return None

        return cls._status_text(value)

    @classmethod
    def _validation_issue_from_raw(
        cls,
        raw: dict,
    ) -> TextToSQLValidationIssue:
        """把 Runtime 中的最终 Issue dict 映射为稳定 TextToSQLValidationIssue。"""

        return TextToSQLValidationIssue(
            rule_id=cls._status_text(
                raw.get("rule_id")
            ),
            source=cls._status_text(
                raw.get("source")
            ),
            severity=cls._status_text(
                raw.get("severity")
            ),
            action=cls._status_text(
                raw.get("action")
            ),
            category=cls._status_text(
                raw.get("category")
            ),
            message=str(
                raw.get(
                    "message",
                    "",
                )
                or ""
            ),
            evidence=str(
                raw.get(
                    "evidence",
                    "",
                )
                or ""
            ),
        )

    @staticmethod
    def _compilation_evidence(
        value,
    ) -> TextToSQLCompilationEvidence | None:
        """
        把内部 CompilationEvidence 映射为公开 Application Projection。

        这里逐字段复制而不是 ``return value``，是为了保证 Application API 不依赖内部
        generation.models 的具体类。未来 Compiler 增加 AST/debug 字段时，不会自动泄漏出去。
        """

        if value is None:
            return None

        return TextToSQLCompilationEvidence(
            metric_names=tuple(
                value.metric_names
            ),
            physical_table=value.physical_table,
            metric_expressions=tuple(
                value.metric_expressions
            ),
            dimension_columns=tuple(
                value.dimension_columns
            ),
            filter_expressions=tuple(
                value.filter_expressions
            ),
            group_by_columns=tuple(
                value.group_by_columns
            ),
        )