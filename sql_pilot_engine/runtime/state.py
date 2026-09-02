from __future__ import annotations

from typing_extensions import (
    NotRequired,
    TypedDict,
)

from sql_pilot_engine.context.builder import (
    QueryContext,
)
from sql_pilot_engine.generation.models import (
    CompilationEvidence,
    QueryPlan,
)
from sql_pilot_engine.linking.models import (
    LinkedSchema,
    SchemaLinkingFailure,
)


class QueryAgentState(TypedDict):
    """
    LangGraph Text-to-SQL Runtime 的共享 State Contract。

    【架构位置】
    QueryAgentGraph 只负责拓扑；QueryRuntimeNodes 负责把每个 Stage 的输入/输出写入 State；
    TextToSQLStageService 才真正调用 Planner / SchemaLinker / Compiler / Generator / Trust /
    Semantic Validator。State 本身只是这些节点之间的“数据总线”，绝不能演变成业务逻辑容器。

    【为什么这里大量使用 NotRequired】
    LangGraph State 是逐节点增量构造的。Planning 之前不可能已经有 QueryPlan，Linking 之前
    也不可能已经有 LinkedSchema。因此不是每个字段在每个阶段都存在。

    【Phase 4.1 新增的关键事实】
    - compilation_status：Compiler 是否成功编译；
    - compilation_fallback_reason：为什么正常回退；
    - compilation_evidence：Compiler 使用的结构化事实；
    - generation_source：当前 SQL Candidate 最终来自 Compiler 还是 LLM。

    注意：compilation_status 与 generation_source 不是同一件事。例如 Compiler 首次成功，
    但 Semantic Validation 后要求用 LLM 重生成时，compilation_status 仍可保留 compiled，
    而 generation_source 会变成 llm。前者回答“Compiler 能不能编”，后者回答“当前 Candidate
    实际是谁生成的”。
    """

    # ========================================================
    # Initial Input / Runtime Identity
    # ========================================================

    # 当前用户问题。start() 时写入，clarification resume 后仍保留原始问题用于上下文构建。
    question: str

    # 产品层 SQL 方言。未传时 Runtime 使用 maxcompute 默认值。
    dialect: NotRequired[str]

    # 会话级补充上下文，不等同于本轮 QueryContext。
    session_context: NotRequired[
        tuple[str, ...]
    ]

    # LangGraph checkpoint / conversation 级身份。
    thread_id: str

    # 单次 turn 的唯一身份，供 Runtime Event / Observability 关联。
    turn_id: str

    # ========================================================
    # Context Intelligence
    # ========================================================

    # 本轮任务上下文快照：语义资产、业务知识、Verified SQL、session context 的组合结果。
    query_context: NotRequired[
        QueryContext | None
    ]

    # ========================================================
    # Planning
    # ========================================================

    # Planner 形成的逻辑查询计划。它描述业务意图，不代表物理字段已经确认。
    query_plan: NotRequired[
        QueryPlan | None
    ]

    # Planner / Trust / Semantic Validation 要求用户补充信息时填写。
    clarification_question: NotRequired[
        str | None
    ]

    # 机器可读的缺失上下文列表，供 HITL 和 Application Response 使用。
    missing_context: NotRequired[
        tuple[str, ...]
    ]

    # 为什么需要澄清，面向开发与产品诊断。
    clarification_reason: NotRequired[
        str
    ]

    # ========================================================
    # Human-in-the-loop
    # ========================================================

    # 已发生的澄清轮次。用于防止 Runtime 无限制 clarification loop。
    clarification_round: NotRequired[int]

    # 本 thread 允许的最大澄清轮数，由 Composition Root 注入到 Nodes 后写入初始 State。
    max_clarification_rounds: NotRequired[int]

    # ========================================================
    # Schema Linking
    # ========================================================

    # QueryPlan 经过物理资产解析后的正式结果。
    linked_schema: NotRequired[
        LinkedSchema | None
    ]

    # Typed Schema Linking Failure。不要仅靠一段 error message 反推具体失败原因。
    linking_failures: NotRequired[
        tuple[
            SchemaLinkingFailure,
            ...
        ]
    ]

    # 面向 Runtime/Application 的可读错误摘要。
    linking_error_message: NotRequired[
        str | None
    ]

    # ========================================================
    # Generation: Compiler Fast Path + LLM Fallback
    # ========================================================

    # Metric Compiler 本轮尝试结果：compiled / not_compilable。
    # 只要 Planning + Linking 后到达 Compiler，就应该有该字段。
    compilation_status: NotRequired[
        str | None
    ]

    # NOT_COMPILABLE 时的稳定机器可读原因；编译成功时必须为 None。
    compilation_fallback_reason: NotRequired[
        str | None
    ]

    # 只有编译成功时存在。它是内部 generation-domain DTO，Application 层会再投影成稳定 DTO。
    compilation_evidence: NotRequired[
        CompilationEvidence | None
    ]

    # 当前 generated_sql 的真实来源：compiled / llm。
    # Compiler fallback 尚未进入 generate_sql 节点时可以暂时为 None。
    generation_source: NotRequired[
        str | None
    ]

    # 当前 SQL Candidate。注意 generated_sql != trusted_sql。
    generated_sql: NotRequired[
        str | None
    ]

    # Semantic Validator 反馈给下一轮 LLM Generator 的修订要求。
    revision_feedback: NotRequired[
        tuple[str, ...]
    ]

    # 已经实际产生过多少个 SQL Candidate，而不是“调用了多少次 LLM”。
    # 因此 Compiler 成功也必须 +1，才能让 semantic retry 上限语义保持一致。
    generation_attempt: NotRequired[int]

    # Semantic Validation 失败后允许再产生多少轮 Candidate。
    max_semantic_retries: NotRequired[int]

    # ========================================================
    # SQL Trust / Validation
    # ========================================================

    # Trust Workflow 接受、但还没完成 Semantic Validation 的中间 SQL。
    candidate_sql: NotRequired[
        str | None
    ]

    # Trust Workflow 的最终机器状态，例如 no_issue / context_required / blocked。
    validation_status: NotRequired[
        str | None
    ]

    validation_error_message: NotRequired[
        str | None
    ]

    # Trust Workflow 最终 Review Issue 的 Runtime 投影。
    validation_issues: NotRequired[
        tuple[
            dict[str, object],
            ...
        ]
    ]

    # ========================================================
    # Semantic Validation
    # ========================================================

    # 判断 Candidate 是否真正满足 QueryPlan 业务语义的结果。
    semantic_validation_status: NotRequired[
        str | None
    ]

    # Semantic Validator 判断只能由用户补充的业务信息。
    semantic_missing_requirements: NotRequired[
        tuple[str, ...]
    ]

    # 可反馈给 LLM 重生成的语义问题列表。
    semantic_issues: NotRequired[
        tuple[str, ...]
    ]

    # ========================================================
    # Final Result
    # ========================================================

    # 完成 Trust + Semantic Validation 后才能进入的最终可信 SQL。
    trusted_sql: NotRequired[
        str | None
    ]

    # 整个 Text-to-SQL turn 是否成功产出最终结果。
    success: NotRequired[bool]

    # 系统/流程失败时的最终摘要；正常 clarification/fallback 不应滥用这个字段。
    error_message: NotRequired[
        str | None
    ]