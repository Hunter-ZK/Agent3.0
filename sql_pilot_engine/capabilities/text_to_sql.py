from __future__ import annotations

from uuid import uuid4

from sql_pilot_engine.runtime.query_graph import (
    QueryAgentGraph,
)

from sql_pilot_engine.schemas.text_to_sql import (
    TextToSQLClarification,
    TextToSQLRequest,
    TextToSQLResponse,
    TextToSQLResult,
)


class TextToSQLCapability:
    """
    Text-to-SQL Application Facade。

    重要边界：

    Service 不再负责：
    - Context Retrieval
    - Planning
    - SQL Generation
    - SQL Validation
    - Semantic Validation
    - Retry
    - Clarification Workflow

    上述流程全部归 QueryAgentGraph。

    Service 只负责：
    - Application Request
    - Runtime start / resume
    - Graph State → Application Response
    """

    def __init__(
        self,
        *,
        graph: QueryAgentGraph,
    ) -> None:

        self._graph = graph

    # ========================================================
    # Public API
    # ========================================================

    def generate(
        self,
        request: TextToSQLRequest,
    ) -> TextToSQLResponse:
        """
        开启一个新的 Text-to-SQL Turn。
        """

        thread_id = uuid4().hex

        state = self._graph.start(
            thread_id=thread_id,

            question=request.question,

            dialect=request.dialect,

            session_context=(
                request.session_context
            ),
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
        从 Clarification / HITL
        继续原有 Runtime Thread。

        注意：
        这里不是重新 generate()。
        """

        normalized_thread_id = (
            thread_id.strip()
        )

        normalized_answer = (
            answer.strip()
        )

        if not normalized_thread_id:
            raise ValueError(
                "thread_id cannot be empty"
            )

        if not normalized_answer:
            raise ValueError(
                "answer cannot be empty"
            )

        state = self._graph.resume(
            thread_id=(
                normalized_thread_id
            ),

            answer=(
                normalized_answer
            ),
        )

        question = str(
            state.get(
                "question",
                "",
            )
            or ""
        ).strip()

        if not question:
            raise RuntimeError(
                "Runtime resumed without "
                "the original question."
            )

        return self._state_to_response(
            state=state,

            question=question,

            thread_id=(
                normalized_thread_id
            ),
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
        将内部 LangGraph State
        转成稳定的 Application DTO。

        这里只做数据转换，
        不做业务判断或 Workflow 路由。
        """

        interrupts = state.get(
            "__interrupt__"
        )

        # ====================================================
        # CLARIFICATION / HITL
        # ====================================================

        if interrupts:

            payload = getattr(
                interrupts[0],
                "value",
                None,
            )

            if not isinstance(
                payload,
                dict,
            ):
                raise RuntimeError(
                    "Invalid LangGraph "
                    "interrupt payload."
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
                    "Clarification question "
                    "is missing."
                )

            return TextToSQLClarification(
                question=question,

                clarification_question=(
                    clarification_question
                ),

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
        # FINAL RESULT
        # ====================================================

        query_plan = state.get(
            "query_plan"
        )

        if query_plan is None:
            raise RuntimeError(
                "Text-to-SQL Runtime "
                "finished without QueryPlan "
                "or clarification."
            )

        semantic_missing_requirements=(
            tuple(
                state.get(
                    "semantic_missing_requirements",
                    (),
                )
                or ()
            )
        ),

        semantic_issues=(
            tuple(
                state.get(
                    "semantic_issues",
                    (),
                )
                or ()
            )
        ),

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

            validation_status=(
                cls._status_text(
                    state.get(
                        "validation_status"
                    )
                )
            ),

            validation_error_message=(
                state.get(
                    "validation_error_message"
                )
            ),

            semantic_validation_status=(
                cls._optional_status_text(
                    state.get(
                        "semantic_validation_status"
                    )
                )
            ),

            semantic_missing_requirements=(
                tuple(
                    getattr(
                        semantic_missing_requirements,
                        "missing_requirements",
                        (),
                    )
                )
            ),

            semantic_issues=tuple(
                getattr(
                    semantic_issues,
                    "issues",
                    (),
                )
            ),
        )

    @staticmethod
    def _status_text(
        value,
    ) -> str:

        if value is None:
            return "not_run"

        enum_value = getattr(
            value,
            "value",
            None,
        )

        if enum_value is not None:
            return str(
                enum_value
            )

        return str(value)

    @classmethod
    def _optional_status_text(
        cls,
        value,
    ) -> str | None:

        if value is None:
            return None

        return cls._status_text(
            value
        )