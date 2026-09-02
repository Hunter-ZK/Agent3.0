from __future__ import annotations

from langgraph.graph import (
    END,
    START,
    StateGraph,
)
from langgraph.types import (
    Command,
)

from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)
from sql_pilot_engine.runtime.query_nodes import (
    QueryRuntimeNodes,
)
from sql_pilot_engine.runtime.state import (
    QueryAgentState,
)


class QueryAgentGraph:
    """
    Agent3.0 Text-to-SQL 的 LangGraph Runtime 拓扑层。

    【核心边界】
    Graph 只回答两个问题：
    1. 下一步执行哪个 Node；
    2. 哪些条件会进入 clarification / retry / end。

    Graph 不实现任何业务算法，也不直接依赖 Planner、SchemaLinker、MetricSQLCompiler、
    SQLGenerator、TrustedSQLWorkflow 或 SemanticSQLValidator。所有业务调用都封装在
    QueryRuntimeNodes -> TextToSQLStageService 中。

    【Phase 4.1 后的主路径】

        START
          ↓
        retrieve_context
          ↓
        plan_query
          ↓
        link_schema
          ↓
        compile_sql
          ├── COMPILED ───────────────→ trust_sql
          └── NOT_COMPILABLE → generate_sql(LLM) → trust_sql
                                              ↓
                                      semantic_validate
                                         ├── PASS → END
                                         ├── clarify → HITL
                                         └── retry → generate_sql(LLM)

    两个容易误改的地方：
    - Compiler 成功后仍然进入 trust_sql，不能直接成为 Trusted SQL；
    - Semantic retry 必须直接回到 generate_sql，而不是 compile_sql。因为同一个结构化输入
      再执行确定性 Compiler 只会得到同一个 SQL，无法吸收 Semantic Validator 的修订反馈。
    """

    def __init__(
        self,
        *,
        nodes: QueryRuntimeNodes,
        checkpoint_store: CheckpointStore,
    ) -> None:
        """
        注入 Node Adapter 与 Checkpoint Store，并编译 LangGraph。

        Checkpoint backend 的创建仍属于 CheckpointStore；Graph 只获取 backend 并交给
        LangGraph.compile。这样未来替换 Memory/SQLite/其它持久化实现时不修改拓扑。
        """

        self.checkpointer = checkpoint_store.get_backend()
        self.nodes = nodes
        self.graph = self._build_graph()

    # ========================================================
    # Graph Definition
    # ========================================================

    def _build_graph(self):
        """
        声明 Text-to-SQL 节点与条件边。

        这里的 route key（如 compile / trust / generate）是 Runtime Node 与 Graph 之间的
        小型控制协议。业务判断发生在 Nodes，Graph 只把返回 key 映射到下一节点。
        """

        builder = StateGraph(
            QueryAgentState
        )

        # ----------------------------------------------------
        # 1. Register nodes
        # ----------------------------------------------------
        # 注册顺序本身不决定执行顺序；真正的顺序由下面的 edge 定义。

        builder.add_node(
            "retrieve_context",
            self.nodes.retrieve_context,
        )
        builder.add_node(
            "plan_query",
            self.nodes.plan_query,
        )
        builder.add_node(
            "link_schema",
            self.nodes.link_schema,
        )
        builder.add_node(
            "compile_sql",
            self.nodes.compile_sql,
        )
        builder.add_node(
            "generate_sql",
            self.nodes.generate_sql,
        )
        builder.add_node(
            "trust_sql",
            self.nodes.trust_sql,
        )
        builder.add_node(
            "semantic_validate",
            self.nodes.semantic_validate,
        )
        builder.add_node(
            "request_clarification",
            self.nodes.request_clarification,
        )

        # ----------------------------------------------------
        # 2. Context -> Planning
        # ----------------------------------------------------

        builder.add_edge(
            START,
            "retrieve_context",
        )
        builder.add_edge(
            "retrieve_context",
            "plan_query",
        )

        # ----------------------------------------------------
        # 3. Planning routing
        # ----------------------------------------------------
        # QueryPlan -> Schema Linking；PlanningClarification -> HITL；
        # 超出允许澄清轮次等不可继续状态 -> END。

        builder.add_conditional_edges(
            "plan_query",
            self.nodes.route_after_plan,
            {
                "link": "link_schema",
                "clarify": "request_clarification",
                "end": END,
            },
        )

        # ----------------------------------------------------
        # 4. Schema Linking routing
        # ----------------------------------------------------
        # 只有 LinkedSchema resolved 才允许进入 Compiler。
        # Linking failure 不应该绕过物理解析直接让 LLM 猜 SQL。

        builder.add_conditional_edges(
            "link_schema",
            self.nodes.route_after_linking,
            {
                "compile": "compile_sql",
                "end": END,
            },
        )

        # ----------------------------------------------------
        # 5. Metric Compiler routing
        # ----------------------------------------------------
        # COMPILED 是快路径，但仍必须进入 Trust；NOT_COMPILABLE 是正常 fallback，
        # 由已有 SQLGenerator 接管。这里不把 fallback 当异常或失败终点。

        builder.add_conditional_edges(
            "compile_sql",
            self.nodes.route_after_compilation,
            {
                "trust": "trust_sql",
                "generate": "generate_sql",
            },
        )

        # LLM Generator 无论是第一次 fallback，还是 Semantic retry，后续都统一进入 Trust。
        builder.add_edge(
            "generate_sql",
            "trust_sql",
        )

        # ----------------------------------------------------
        # 6. Trusted SQL routing
        # ----------------------------------------------------
        # Trust Gate 只判断 SQL 是否可接受。需要业务上下文时进入 clarification；
        # 被接受的 candidate 还要继续 Semantic Validation，不能直接 END 为成功。

        builder.add_conditional_edges(
            "trust_sql",
            self.nodes.route_after_trust,
            {
                "semantic_validate": "semantic_validate",
                "clarify": "request_clarification",
                "end": END,
            },
        )

        # ----------------------------------------------------
        # 7. Semantic Validation routing
        # ----------------------------------------------------
        # retry 明确指向 LLM generate_sql，而不是 compile_sql：Semantic Validator 的 feedback
        # 需要能影响下一轮 Candidate，而确定性 Compiler 不消费 revision_feedback。

        builder.add_conditional_edges(
            "semantic_validate",
            self.nodes.route_after_semantic_validation,
            {
                "retry": "generate_sql",
                "clarify": "request_clarification",
                "end": END,
            },
        )

        # ----------------------------------------------------
        # 8. HITL resume routing
        # ----------------------------------------------------
        # 用户补充信息后重新构建 QueryContext 再 Planning，而不是从中间状态硬接着生成 SQL。

        builder.add_conditional_edges(
            "request_clarification",
            self.nodes.route_after_clarification,
            {
                "continue": "retrieve_context",
                "end": END,
            },
        )

        return builder.compile(
            checkpointer=self.checkpointer
        )

    def start(
        self,
        *,
        thread_id: str,
        question: str,
        dialect: str = "maxcompute",
        session_context: tuple[str, ...] = (),
    ) -> dict:
        """
        启动一个新的 Text-to-SQL Runtime thread。

        thread_id 用于 LangGraph checkpoint；turn_id 等更细粒度运行身份由 Nodes 的
        build_initial_state 负责创建，避免 Graph 自己维护业务 State 字段。
        """

        normalized_thread_id = thread_id.strip()
        normalized_question = question.strip()

        if not normalized_thread_id:
            raise ValueError(
                "thread_id cannot be empty"
            )

        if not normalized_question:
            raise ValueError(
                "question cannot be empty"
            )

        config = {
            "configurable": {
                "thread_id": normalized_thread_id,
            }
        }

        initial_state = self.nodes.build_initial_state(
            thread_id=normalized_thread_id,
            question=normalized_question,
            dialect=dialect,
            session_context=session_context,
        )

        return self.graph.invoke(
            initial_state,
            config=config,
        )

    def resume(
        self,
        *,
        thread_id: str,
        answer: str,
    ) -> dict:
        """
        向已 interrupt 的 LangGraph thread 提交用户澄清答案并恢复执行。

        这里使用 Command(resume=...) 恢复原 checkpoint，不重新创建一个新的 generate()。
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

        config = {
            "configurable": {
                "thread_id": normalized_thread_id,
            }
        }

        return self.graph.invoke(
            Command(
                resume=normalized_answer
            ),
            config=config,
        )