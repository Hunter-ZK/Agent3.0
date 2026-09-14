from __future__ import annotations

import json
from typing import Any


CTE_EXPLAIN_BATCH_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "cte_explanations": {"type": "array"},
    },
    "required": ["cte_explanations"],
}


EXPLAIN_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "sql_summary": {"type": "string"},
        "business_purpose": {},
        "statement_explanations": {"type": "array"},
        "table_roles": {"type": "array"},
        "output_column_explanations": {"type": "array"},
        "key_transformations": {"type": "array"},
        "suspicious_points": {"type": "array"},
        "uncertainties": {"type": "array"},
        "route_signals": {"type": "object"},
    },
    "required": [
        "sql_summary",
        "statement_explanations",
        "table_roles",
        "output_column_explanations",
        "key_transformations",
        "suspicious_points",
        "uncertainties",
        "route_signals",
    ],
}


EXPLAIN_SYSTEM_PROMPT = """
你是生产级 MaxCompute / DataWorks SQL Explain 模型。

你的职责不是重新解析 SQL，而是在 Agent3 已经确定的 Program / Metadata / Lineage /
Hint 事实之上补充业务语义解释。

强约束：
- Deterministic Context 是 statement、CTE dependency、physical table、write target、partition、lineage、hint 的最高优先级事实；
- 不得创造输入中不存在的表、字段、CTE、写入目标、依赖关系或 lineage；
- Metadata / Lineage 不完整时必须写入 uncertainties，不得猜测为确定事实；
- 业务目的、字段意义、CTE 作用可以做保守推断，但必须基于 SQL 片段、命名、Metadata 或上游语义；
- 不知道就明确说不知道，不用为了完整性编造业务口径；
- suspicious_points 只描述值得 Review 的语义或工程风险，不直接宣称 SQL 错误；
- 只能返回 JSON object。
""".strip()


CTE_EXPLAIN_SYSTEM_PROMPT = """
你负责生产 SQL 的局部 CTE 语义解释。

每个 CTE 都附带 Agent3 确定性事实和该 CTE 自己的受控 SQL 片段。
请逐个解释，不要跨 CTE 编造事实。

每个 cte_explanations 元素建议包含：
- statement_index
- name
- purpose：这个 CTE 在数据流程中的作用
- processing_logic：关键过滤、关联、聚合、展开、去重、口径变换
- business_semantics：能够保守确认的业务语义
- input_semantics：输入数据在本步骤扮演的角色
- output_semantics：本步骤产出数据的含义
- confidence：0~1
- uncertainties：无法确认的内容

name 和 statement_index 必须与输入完全一致。
只返回 JSON object。
""".strip()


def build_cte_explain_user_prompt(
    *,
    cte_batch: list[dict[str, Any]],
) -> str:
    return f"""
## CTE deterministic chunks

```json
{json.dumps(cte_batch, ensure_ascii=False, indent=2)}
```

逐个解释上述 CTE。

注意：
- dependencies、physical_sources、output_columns、aggregates、predicates 属于确定性事实；
- sql_excerpt 只代表该 CTE 的受控代码片段；
- output_complete=false 时，不要假设已看到全部输出字段；
- unresolved_sources 非空时必须在 uncertainties 中说明。
""".strip()


def build_explain_user_prompt(
    *,
    program_context: dict[str, Any],
    cte_explanations: list[dict[str, Any]],
) -> str:
    return f"""
## Deterministic Program / Evidence Context

```json
{json.dumps(program_context, ensure_ascii=False, indent=2)}
```

## CTE semantic explanations

```json
{json.dumps(cte_explanations, ensure_ascii=False, indent=2)}
```

请输出整份生产 SQL Program 的解释结果：

1. sql_summary
   面向数据开发人员，用 2~5 句话说明整份程序做什么、主要输入、核心加工、最终写到哪里。

2. business_purpose
   只写能够确认或保守推断的业务目的；证据不足可为 null。

3. statement_explanations
   每个业务 Statement 一项，至少包含 statement_index、purpose、inputs、processing_flow、write_target、partition_behavior、uncertainties。
   statement_index 必须来自 Deterministic Context。

4. table_roles
   对确定性 main/read/write table 补充 business_role / usage_summary；不得增加不存在的表。

5. output_column_explanations
   只针对 Deterministic Lineage 已提供的目标字段补充 meaning / derivation_summary / confidence / uncertainties；
   target 必须原样使用 Deterministic Context 中的 target。

6. key_transformations
   总结真正重要的业务/技术变换，例如过滤、JOIN、聚合、UNION、GROUPING SETS、EXPLODE、窗口、去重、币种/口径转换等。
   每项建议包含 location、type、description、business_impact、confidence。

7. suspicious_points / uncertainties
   清楚区分“值得 Review”与“证据不足”。

8. route_signals
   给出 need_metadata、need_review、need_human_confirm；不要声称可以自动修复生产语义问题。

CTE semantic explanations 是局部语义增强，不得覆盖 Deterministic Program/Evidence 事实。
""".strip()
