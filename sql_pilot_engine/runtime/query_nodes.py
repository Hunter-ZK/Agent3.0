from __future__ import annotations

import logging
from uuid import uuid4

from langgraph.types import interrupt

from sql_pilot_engine.generation.models import (
    CompilationStatus,
    GenerationSource,
    PlanningClarification,
)
from sql_pilot_engine.linking.schema_linker import (
    SchemaLinkingError,
)
from sql_pilot_engine.runtime.event import (
    RuntimeEvent,
    RuntimeEventType,
)
from sql_pilot_engine.runtime.event_bus import (
    EventBus,
)
from sql_pilot_engine.runtime.state import (
    QueryAgentState,
)
from sql_pilot_engine.services.semantic_validation_service import (
    SemanticValidationResult,
    SemanticValidationStatus,
)
from sql_pilot_engine.services.text_to_sql_stage_service import (
    TextToSQLStageService,
)

logger = logging.getLogger(__name__)


class QueryRuntimeNodes:
    """
    Text-to-SQL LangGraph 的 Runtime Node Adapter。

    【架构位置】

        QueryAgentGraph                —— 只定义拓扑
            ↓
        QueryRuntimeNodes              —— 本类：State / Routing / Retry / HITL Adapter
            ↓
        TextToSQLStageService          —— 调用各业务 Stage
            ↓
        Planner / Linker / Compiler / Generator / Trust / Semantic Validator

    每个 Node 的标准职责是：
    1. 从 QueryAgentState 读取当前 Stage 必需输入；
    2. 检查上游 Contract 是否完整，缺失时抛 RuntimeError；
    3. 调用 StageService；
    4. 把结果转换成下一节点需要的 State update；
    5. 必要时发布旁路 Runtime Event。

    本类可以负责“下一步该走哪条边”，但不能自己实现业务算法。具体来说，它不负责：
    - Context Retrieval 算法；
    - Planning / Schema Linking 算法；
    - Metric Compilation / SQL Generation 算法；
    - Trusted SQL 内部 review/fix/critic；
    - Semantic Validation 算法；
    - Graph topology；
    - Checkpoint backend；
    - Capability start / resume API。

    【Phase 4.1 最重要的 Runtime 语义】
    - link_schema 成功后先进入 compile_sql；
    - COMPILED -> trust_sql；
    - NOT_COMPILABLE -> generate_sql(LLM)；
    - Compiler 成功也必须增加 generation_attempt，因为它已经产生了一个 SQL Candidate；
    - Semantic retry 永远直接走 generate_sql，而不是再次 compile_sql。
    """

    def __init__(
        self,
        *,
        stage_service: TextToSQLStageService,
        event_bus: EventBus,
        max_semantic_retries: int = 1,
        max_clarification_rounds: int = 3,
    ) -> None:
        """注入 StageService、EventBus 与 Runtime 级重试/澄清上限。"""

        if max_semantic_retries < 0:
            raise ValueError(
                "max_semantic_retries must be >= 0"
            )

        if max_clarification_rounds <= 0:
            raise ValueError(
                "max_clarification_rounds must be greater than 0"
            )

        self.stage_service = stage_service
        self.event_bus = event_bus
        self.max_semantic_retries = max_semantic_retries
        self.max_clarification_rounds = max_clarification_rounds

    def _publish_event(
        self,
        *,
        state: QueryAgentState,
        event_type: RuntimeEventType,
        stage: str,
        data: dict[str, object] | None = None,
    ) -> None:
        """
        Runtime Event 的统一旁路出口。

        Observability 不能反向控制业务结果：即使 Event Sink 暂时不可用，Text-to-SQL 主链也
        应继续执行。因此这里捕获 publish 异常并记录日志，而不是让监控故障变成用户查询故障。
        """

        event = RuntimeEvent(
            event_type=event_type,
            capability="text_to_sql",
            thread_id=state["thread_id"],
            turn_id=state["turn_id"],
            stage=stage,
            data=data if data is not None else {},
        )

        try:
            self.event_bus.publish(event)
        except Exception:
            # EventBus 是旁路能力，这里必须 fail-open；业务链的异常仍由各 Node 正常抛出。
            logger.exception(
                "Runtime event publish failed: type=%s stage=%s",
                event_type.value,
                stage,
            )

    # ========================================================
    # Node 1: Context Intelligence
    # ========================================================

    def retrieve_context(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        以原始 question + 当前 session_context 构建本轮 QueryContext。

        clarification resume 后也会重新经过本节点，因为用户新补充的信息已经被加入
        session_context，需要重新形成任务上下文，而不是继续使用旧 QueryContext。
        """

        question = state["question"]
        query_context = self.stage_service.build_query_context(
            question=question,
            session_context=state.get(
                "session_context",
                (),
            ),
        )

        return {
            "query_context": query_context,
        }

    # ========================================================
    # Node 2: Planning
    # ========================================================

    def plan_query(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        调用 Planner，并把“QueryPlan / 需要澄清”转成 Runtime State。

        PlanningClarification 是正常业务分支，不是异常。真正缺失 query_context 才属于
        Runtime Contract 破坏。
        """

        query_context = state.get(
            "query_context"
        )
        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing before planning."
            )

        outcome = self.stage_service.plan(
            query_context=query_context,
        )

        if isinstance(
            outcome,
            PlanningClarification,
        ):
            self._publish_event(
                state=state,
                event_type=RuntimeEventType.PLAN,
                stage="planning",
                data={
                    "status": "clarification_required",
                },
            )

            return {
                # 显式清除旧 QueryPlan，避免 clarification loop 中上一轮计划残留。
                "query_plan": None,
                "clarification_question": outcome.clarification_question,
                "missing_context": outcome.missing_context,
                "clarification_reason": outcome.reason,
                "success": False,
            }

        # 新 QueryPlan 产生后，Linking 及其之后所有 request-scoped 中间状态都应重新计算。
        return {
            "query_plan": outcome,
            "clarification_question": None,
            "missing_context": (),
            "clarification_reason": "",
            "success": False,
            "linked_schema": None,
            "linking_failures": (),
            "linking_error_message": None,
        }

    # ========================================================
    # Node 3: Schema Linking
    # ========================================================

    def link_schema(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        把 QueryPlan 解析为 LinkedSchema，并把 typed failure 保存进 Runtime State。

        Linker 不 resolved 时禁止继续让 Compiler/Generator 猜物理字段；Graph 会在
        route_after_linking() 结束本轮。
        """

        plan = state.get(
            "query_plan"
        )
        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing before schema linking."
            )

        try:
            linked_schema = self.stage_service.link_schema(
                plan=plan
            )
        except SchemaLinkingError as error:
            # SchemaLinkingError 表示 Linker 自身无法形成正常 LinkedSchema 结果。
            message = str(error)
            return {
                "linked_schema": None,
                "linking_failures": (),
                "linking_error_message": message,
                "error_message": message,
                "success": False,
            }

        if not linked_schema.resolved:
            failures = linked_schema.failures
            message = self._build_linking_error_message(
                failures
            )

            return {
                "linked_schema": linked_schema,
                "linking_failures": failures,
                "linking_error_message": message,
                "error_message": message,
                "success": False,
            }

        return {
            "linked_schema": linked_schema,
            "linking_failures": (),
            "linking_error_message": None,
            "error_message": None,
        }

    # ========================================================
    # Node 4: Deterministic Metric Compilation
    # ========================================================

    def compile_sql(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        尝试把 QueryPlan + LinkedSchema 编译成确定性 SQL Candidate。

        【为什么这个 Node 必须独立存在】
        Compiler 是否成功会影响 Graph 下一条边，属于 Runtime 可观测控制状态：
        - COMPILED：写入 generated_sql / generation_source=compiled，然后去 Trust；
        - NOT_COMPILABLE：只记录 fallback 原因，不制造 SQL，下一步去 LLM Generator。

        Node 不解释为什么某种业务结构不可编译，具体能力边界属于 MetricSQLCompiler。
        """

        plan = state.get(
            "query_plan"
        )
        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing before Metric compilation."
            )

        linked_schema = state.get(
            "linked_schema"
        )
        if linked_schema is None:
            raise RuntimeError(
                "LinkedSchema is missing before Metric compilation."
            )

        outcome = self.stage_service.try_compile_sql(
            plan=plan,
            linked_schema=linked_schema,
            dialect=state.get(
                "dialect",
                "maxcompute",
            ),
        )

        # 无论成功还是 fallback，都记录“Compiler 实际尝试过”的可观测结果。
        updates = {
            "compilation_status": outcome.status.value,
            "compilation_fallback_reason": (
                outcome.fallback_reason.value
                if outcome.fallback_reason is not None
                else None
            ),
            "compilation_evidence": outcome.evidence,
        }

        if outcome.status is CompilationStatus.COMPILED:
            generated = outcome.generated_sql

            # DTO 自身已经保护这个不变量；Node 再检查一次是 Runtime boundary 的防御式校验。
            if generated is None:
                raise RuntimeError(
                    "Compiler returned COMPILED without SQL."
                )

            # generation_attempt 表示“已产生多少个 SQL Candidate”，而不是 LLM 调用次数。
            # Compiler 成功也已经消耗一次 Candidate 尝试，所以必须 +1；否则 semantic retry
            # 会比配置多放行一轮 LLM 生成。
            attempt = state.get(
                "generation_attempt",
                0,
            ) + 1

            updates.update(
                {
                    "generated_sql": generated.sql,
                    "generation_source": GenerationSource.COMPILED.value,
                    "generation_attempt": attempt,
                }
            )
            return updates

        # NOT_COMPILABLE 是正常 fallback：必须清空 SQL/source，让下一节点明确产生新的 LLM Candidate。
        updates.update(
            {
                "generated_sql": None,
                "generation_source": None,
            }
        )
        return updates

    # ========================================================
    # Node 5: LLM SQL Generation
    # ========================================================

    def generate_sql(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        生成 LLM SQL Candidate。

        这个 Node 既服务 Compiler fallback，也服务 Semantic Validation retry。每次真正生成新
        Candidate 都增加 generation_attempt，并把 generation_source 覆盖为 llm。
        """

        attempt = state.get(
            "generation_attempt",
            0,
        ) + 1

        query_context = state.get(
            "query_context"
        )
        linked_schema = state.get(
            "linked_schema"
        )
        plan = state.get(
            "query_plan"
        )

        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing before SQL generation."
            )
        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing before SQL generation."
            )
        if linked_schema is None:
            raise RuntimeError(
                "LinkedSchema is missing before SQL generation."
            )

        result = self.stage_service.generate_sql(
            plan=plan,
            linked_schema=linked_schema,
            query_context=query_context,
            dialect=state.get(
                "dialect",
                "maxcompute",
            ),
            revision_feedback=state.get(
                "revision_feedback",
                (),
            ),
        )

        return {
            "generated_sql": result.sql,
            "generation_attempt": attempt,
            "generation_source": GenerationSource.LLM.value,
        }

    # ========================================================
    # Node 6: Trusted SQL Workflow
    # ========================================================

    def trust_sql(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        把当前 SQL Candidate 送入统一 Trusted SQL Workflow。

        generation_source 在这里不是装饰字段：StageService 会据此决定 compiled path 是否显式
        关闭 LLM Review。无论来源是什么，Trust Workflow 都必须执行，Compiler 不能绕过 Gate。
        """

        plan = state.get(
            "query_plan"
        )
        linked_schema = state.get(
            "linked_schema"
        )
        query_context = state.get(
            "query_context"
        )
        generated_sql = state.get(
            "generated_sql"
        )

        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing before Trusted SQL workflow."
            )
        if linked_schema is None:
            raise RuntimeError(
                "LinkedSchema is missing before Trusted SQL workflow."
            )
        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing before Trusted SQL workflow."
            )
        if not generated_sql:
            raise RuntimeError(
                "Generated SQL is missing before Trusted SQL workflow."
            )

        generation_source_value = state.get(
            "generation_source"
        )
        if not generation_source_value:
            raise RuntimeError(
                "generation_source is missing before Trusted SQL workflow."
            )

        try:
            generation_source = GenerationSource(
                generation_source_value
            )
        except ValueError as exc:
            raise RuntimeError(
                "Invalid generation_source: "
                f"{generation_source_value}"
            ) from exc

        trust_result = self.stage_service.trust_sql(
            generated_sql=generated_sql,
            dialect=state.get(
                "dialect",
                "maxcompute",
            ),
            query_context=query_context,
            plan=plan,
            linked_schema=linked_schema,
            generation_source=generation_source,
        )

        missing_context = tuple(
            trust_result.missing_context
            or ()
        )

        # success=True 却没有 trusted_sql 会让后续 Semantic Validator 没有输入，属于 Contract 破坏。
        if trust_result.success and not trust_result.trusted_sql:
            raise RuntimeError(
                "TrustedSQLWorkflow succeeded without trusted_sql."
            )

        self._publish_event(
            state=state,
            event_type=RuntimeEventType.VALIDATION,
            stage="trusted_sql",
            data={
                "status": trust_result.final_status,
            },
        )

        updates = {
            # 暂时保留现有 public/state 字段名；这里表示 Trust Workflow 的最终状态。
            "validation_status": trust_result.final_status,
            "validation_error_message": trust_result.error_message,
            "validation_issues": tuple(
                trust_result.validation_issues
                or ()
            ),
            "missing_context": missing_context,

            # candidate_sql 仅表示“Trust 已接受”，还没有通过 Semantic Validation。
            # 所以此处明确不写 trusted_sql，也不把 success 设为 True。
            "candidate_sql": trust_result.trusted_sql,
            "trusted_sql": None,
            "success": False,
        }

        if trust_result.final_status == "context_required":
            updates.update(
                {
                    "clarification_question": self._build_validation_clarification(
                        missing_context
                    ),
                    "missing_context": missing_context,
                    "clarification_reason": (
                        trust_result.error_message
                        or "Trusted SQL 审查发现仍缺少必要业务上下文。"
                    ),
                }
            )
        else:
            # 非 clarification 路径必须清掉上一轮 HITL 字段，防止 checkpoint 中旧状态误触发路由。
            updates.update(
                {
                    "missing_context": (),
                    "clarification_question": None,
                    "clarification_reason": "",
                }
            )

        return updates

    # ========================================================
    # Node 7: Semantic Validation
    # ========================================================

    def semantic_validate(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        判断 Trust Candidate 是否真正满足 QueryPlan 业务语义。

        三类结果：
        - PASS：candidate_sql 升级为最终 trusted_sql；
        - NEED_CLARIFICATION：转入 HITL；
        - 其它失败：生成 revision_feedback，若重试额度允许则 Graph 直接回到 LLM generate_sql。

        如果没有配置 Semantic Validator，保持现有兼容语义：Trust Candidate 直接成为最终结果。
        """

        candidate_sql = state.get(
            "candidate_sql"
        )
        plan = state.get(
            "query_plan"
        )
        query_context = state.get(
            "query_context"
        )

        if not candidate_sql:
            raise RuntimeError(
                "candidate_sql is missing before Semantic Validation."
            )
        if plan is None:
            raise RuntimeError(
                "QueryPlan is missing before Semantic Validation."
            )
        if query_context is None:
            raise RuntimeError(
                "QueryContext is missing before Semantic Validation."
            )

        result = self.stage_service.validate_semantics(
            sql=candidate_sql,
            plan=plan,
            query_context=query_context,
        )

        if result is None:
            # Semantic Validator 未启用时，Trust Candidate 即为最终 SQL；这不是伪造一个 PASS 枚举。
            self._publish_event(
                state=state,
                event_type=RuntimeEventType.AGENT_RESULT,
                stage="result",
                data={
                    "success": True,
                },
            )

            return {
                "semantic_result": None,
                "semantic_validation_status": None,
                "trusted_sql": candidate_sql,
                "success": True,
            }

        self._publish_event(
            state=state,
            event_type=RuntimeEventType.VALIDATION,
            stage="semantic_validation",
            data={
                "status": result.status.value,
            },
        )

        updates: dict = {
            "semantic_validation_status": result.status.value,
            "semantic_missing_requirements": tuple(
                result.missing_requirements
            ),
            "semantic_issues": tuple(
                result.issues
            ),
        }

        if result.passed:
            updates.update(
                {
                    "trusted_sql": candidate_sql,
                    "success": True,
                    "revision_feedback": (),
                }
            )

            self._publish_event(
                state=state,
                event_type=RuntimeEventType.AGENT_RESULT,
                stage="result",
                data={
                    "success": True,
                },
            )
            return updates

        if result.status is SemanticValidationStatus.NEED_CLARIFICATION:
            updates.update(
                {
                    "trusted_sql": None,
                    "success": False,
                    "clarification_question": self._build_semantic_clarification(
                        result
                    ),
                    "missing_context": result.missing_requirements,
                }
            )
            return updates

        # 可修订的语义失败不在这里直接调用 LLM；Node 只写 feedback，Graph 再决定 retry 边。
        updates.update(
            {
                "trusted_sql": None,
                "success": False,
                "revision_feedback": self.build_revision_feedback(
                    result
                ),
            }
        )
        return updates

    # ========================================================
    # Routing
    # ========================================================

    @staticmethod
    def route_after_plan(
        state: QueryAgentState,
    ) -> str:
        """Planning 后：系统错误结束；需要业务信息则澄清；否则继续 Linking。"""

        if state.get("error_message"):
            return "end"
        if state.get("clarification_question"):
            return "clarify"
        return "link"

    @staticmethod
    def route_after_linking(
        state: QueryAgentState,
    ) -> str:
        """
        Linking 后只有 resolved LinkedSchema 才能进入 Compiler。

        这里不提供“linking 失败也去 LLM”的逃生口，因为那会让 LLM 绕过物理事实层猜字段。
        """

        linked_schema = state.get(
            "linked_schema"
        )

        if state.get("error_message"):
            return "end"
        if linked_schema is None:
            return "end"
        if not linked_schema.resolved:
            return "end"
        return "compile"

    @staticmethod
    def route_after_compilation(
        state: QueryAgentState,
    ) -> str:
        """
        Compiler 成功走 Trust，正常能力边界 fallback 走 LLM Generator。

        未知/缺失 status 不是 fallback，而是 Runtime Contract 破坏，因此显式抛异常。
        """

        status = state.get(
            "compilation_status"
        )

        if status == CompilationStatus.COMPILED.value:
            return "trust"
        if status == CompilationStatus.NOT_COMPILABLE.value:
            return "generate"

        raise RuntimeError(
            "Metric Compiler finished without a valid status."
        )

    @staticmethod
    def route_after_trust(
        state: QueryAgentState,
    ) -> str:
        """Trust 后：缺上下文 -> clarify；没有 Candidate -> end；否则继续 Semantic Validation。"""

        if state.get("validation_status") == "context_required":
            if not state.get("missing_context"):
                raise RuntimeError(
                    "Trusted SQL returned context_required without missing_context."
                )
            return "clarify"

        if state.get("candidate_sql") is None:
            return "end"

        return "semantic_validate"

    @staticmethod
    def route_after_semantic_validation(
        state: QueryAgentState,
    ) -> str:
        """
        Semantic Validation 后决定结束、澄清或 LLM retry。

        generation_attempt 统计已经产生的 Candidate 数。默认 max_semantic_retries=1 时：
        第一个 Candidate 的 attempt=1，若语义失败，1 <= 1，允许再生成一个 LLM Candidate；
        第二个 Candidate attempt=2，再失败时 2 <= 1 为 False，结束。
        """

        status = state.get(
            "semantic_validation_status"
        )

        # Semantic Validator 未启用时 semantic_validate 已经完成最终结果，因此结束。
        if status is None:
            return "end"

        if status == SemanticValidationStatus.PASS.value:
            return "end"

        if status == SemanticValidationStatus.NEED_CLARIFICATION.value:
            return "clarify"

        attempt = state.get(
            "generation_attempt",
            0,
        )
        max_retries = state.get(
            "max_semantic_retries",
            0,
        )

        if attempt <= max_retries:
            # Graph 中 retry 边直接指向 generate_sql，绝不回到 deterministic compile_sql。
            return "retry"

        return "end"

    @staticmethod
    def route_after_clarification(
        state: QueryAgentState,
    ) -> str:
        """HITL 节点拿到有效答案后重新进入 Context Intelligence；失败则结束。"""

        if state.get("error_message"):
            return "end"
        return "continue"

    # ========================================================
    # Human-in-the-loop
    # ========================================================

    def request_clarification(
        self,
        state: QueryAgentState,
    ) -> dict:
        """
        暂停 Graph 并向用户请求必要业务上下文。

        第一次执行：``interrupt(payload)`` 暂停 Graph。
        resume 后：节点会重新执行到 interrupt，随后 interrupt 返回 ``Command(resume=...)`` 的值。

        因此 interrupt 之前不能做不可重复的业务副作用；当前只构造 payload，没有写数据库等操作。
        """

        current_round = state.get(
            "clarification_round",
            0,
        )
        max_rounds = state.get(
            "max_clarification_rounds",
            self.max_clarification_rounds,
        )

        if current_round >= max_rounds:
            return {
                "success": False,
                "error_message": "Agent连续多次仍无法获得足够上下文，任务停止。",
                "clarification_question": None,
            }

        payload = {
            "type": "clarification",
            "question": state.get(
                "clarification_question"
            ),
            "missing_context": state.get(
                "missing_context",
                (),
            ),
            "reason": state.get(
                "clarification_reason",
                "",
            ),
            "round": current_round + 1,
            "max_rounds": max_rounds,
        }

        answer = interrupt(payload)
        answer_text = str(answer).strip()

        if not answer_text:
            return {
                "success": False,
                "error_message": "用户未提供有效澄清信息。",
                "clarification_question": None,
            }

        existing_context = state.get(
            "session_context",
            (),
        )
        new_session_context = (
            *existing_context,
            f"User clarification: {answer_text}",
        )

        # 用户答案会让 Planning 及其后的所有阶段重新执行，因此必须清掉上一轮 request-scoped
        # 中间结果。尤其是 Phase 4.1 的 compilation_status/evidence/source，如果不清理，在新的
        # Planning 尚未到达 Compiler 前会残留上一轮事实，污染 checkpoint 与观测结果。
        return {
            "session_context": new_session_context,
            "clarification_round": current_round + 1,

            # Planning / Linking reset
            "query_context": None,
            "query_plan": None,
            "linked_schema": None,
            "linking_failures": (),
            "linking_error_message": None,

            # Clarification reset
            "clarification_question": None,
            "missing_context": (),
            "clarification_reason": "",

            # Generation reset
            "compilation_status": None,
            "compilation_fallback_reason": None,
            "compilation_evidence": None,
            "generation_source": None,
            "generated_sql": None,
            "revision_feedback": (),
            "generation_attempt": 0,

            # Trust / Semantic reset
            "validation_status": None,
            "validation_error_message": None,
            "validation_issues": (),
            "candidate_sql": None,
            "semantic_result": None,
            "semantic_validation_status": None,
            "semantic_missing_requirements": (),
            "semantic_issues": (),

            # Final reset
            "trusted_sql": None,
            "success": False,
            "error_message": None,
        }

    # ========================================================
    # Feedback / Clarification Helpers
    # ========================================================

    @staticmethod
    def build_revision_feedback(
        result: SemanticValidationResult,
    ) -> tuple[str, ...]:
        """
        把 Semantic Validation 结构化问题转成下一轮 SQLGenerator 可消费的文本反馈。

        这里不修改 QueryPlan，也不自己修 SQL；它只是跨 Stage 的最小反馈适配。
        """

        feedback: list[str] = []

        for requirement in result.missing_requirements:
            feedback.append(
                "Missing requirement: "
                f"{requirement}"
            )

        for issue in result.issues:
            feedback.append(
                "Semantic issue: "
                f"{issue}"
            )

        if not feedback:
            feedback.append(
                "The previous SQL did not fully satisfy the original "
                "question. Re-evaluate the complete request."
            )

        return tuple(feedback)

    @staticmethod
    def _build_semantic_clarification(
        result: SemanticValidationResult,
    ) -> str:
        """把 Semantic Validator 的 missing_requirements 转成面向用户的澄清问题。"""

        if result.missing_requirements:
            details = "；".join(
                result.missing_requirements
            )
            return (
                "当前还缺少以下必要信息："
                f"{details}"
            )

        return (
            "当前上下文不足以可靠完成查询，"
            "请补充必要的业务信息。"
        )

    @staticmethod
    def _build_validation_clarification(
        missing_context: tuple[str, ...],
    ) -> str:
        """
        把 Trust Workflow 的 CONTEXT_REQUIRED 证据转成用户澄清问题。

        context_required 却没有 missing_context 属于内部 Contract 错误，不能生成一个空泛问题掩盖它。
        """

        if not missing_context:
            raise RuntimeError(
                "context_required must provide missing_context."
            )

        details = "；".join(
            missing_context
        )
        return (
            "为了继续完成当前查询，"
            "还需要确认以下信息："
            f"{details}"
        )

    @staticmethod
    def _build_linking_error_message(
        failures,
    ) -> str:
        """把 typed SchemaLinkingFailure 列表投影成可读错误摘要，同时保留原 typed failures。"""

        if not failures:
            return "Schema linking failed."

        details = "; ".join(
            f"{failure.code.value}: {failure.term}"
            for failure in failures
        )
        return (
            "Schema linking failed: "
            f"{details}"
        )

    # ========================================================
    # Initial State
    # ========================================================

    def build_initial_state(
        self,
        *,
        thread_id: str,
        question: str,
        dialect: str,
        session_context: tuple[str, ...],
    ) -> QueryAgentState:
        """
        为新的 Text-to-SQL Turn 构建完整、干净的初始 State。

        同一个 thread_id 可以跨多个 Turn，因此不能依赖 checkpoint 中“字段不存在就是空”的偶然
        状态。所有 request-scoped 中间字段都显式初始化，避免上一 Turn 的 Compiler/Trust/Semantic
        状态泄漏到新请求。
        """

        state: QueryAgentState = {
            # Runtime Identity
            "thread_id": thread_id,
            "turn_id": str(uuid4()),

            # Input
            "question": question,
            "dialect": dialect,
            "session_context": session_context,

            # Context / Planning
            "query_context": None,
            "query_plan": None,
            "clarification_question": None,
            "missing_context": (),
            "clarification_reason": "",

            # HITL
            "clarification_round": 0,
            "max_clarification_rounds": self.max_clarification_rounds,

            # Schema Linking
            "linked_schema": None,
            "linking_failures": (),
            "linking_error_message": None,

            # Generation / Compiler
            "compilation_status": None,
            "compilation_fallback_reason": None,
            "compilation_evidence": None,
            "generation_source": None,
            "generated_sql": None,
            "revision_feedback": (),
            "generation_attempt": 0,
            "max_semantic_retries": self.max_semantic_retries,

            # Trusted SQL
            "validation_status": None,
            "validation_error_message": None,
            "validation_issues": (),
            "candidate_sql": None,

            # Semantic Validation
            "semantic_validation_status": None,
            "semantic_missing_requirements": (),
            "semantic_issues": (),

            # Final
            "trusted_sql": None,
            "success": False,
            "error_message": None,
        }

        # USER_MESSAGE event 是旁路观测，不参与 Graph routing。
        self._publish_event(
            state=state,
            event_type=RuntimeEventType.USER_MESSAGE,
            stage="input",
            data={
                "status": "received",
            },
        )

        return state