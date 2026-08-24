
import json
from typing import Any
from sql_pilot_engine.core.models import (
    Issue,
)
from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.llm.context_builder import (
    build_query_context_text,
)

LLM_REVIEW_JSON_SCHEMA = {
    "name": "sql_review_result",
    "schema": {
        "type": "object",
        "properties": {
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rule_id": {
                            "type": "string",
                        },
                        "title": {
                            "type": "string",
                        },
                        "severity": {
                            "type": "string",
                            "enum": [
                                "low",
                                "medium",
                                "high",
                            ],
                        },
                        "message": {
                            "type": "string",
                        },
                        "suggestion": {
                            "type": "string",
                        },
                        "evidence": {
                            "type": "string",
                        },
                        "category": {
                            "type": "string",
                        },
                        "confidence": {
                            "type": "number",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "advisory",
                                "auto_fix",
                                "context_required",
                                "human_review",
                            ],
                        },
                    },
                    "required": [
                        "rule_id",
                        "title",
                        "severity",
                        "message",
                        "suggestion",
                        "evidence",
                        "category",
                        "confidence",
                        "action",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": [
            "issues"
        ],
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = """
你是 Agent3.0 的 SQL 智能审查器。

系统已经使用 SQLGlot、确定性 Guardrails
和 MetadataValidator 处理能够明确判断的硬事实。

你的主要职责是处理需要 SQL 理解、业务语义
和上下文推理的问题。

重点关注但不限于：

- JOIN 语义与数据放大风险
- 聚合粒度与指标口径
- NULL 处理
- 过滤条件合理性
- 日期与调度语义
- 分区使用合理性
- 数据粒度
- SQL 业务语义一致性
- 可维护性
- 性能风险

不要因为没有对应 Python Rule 就忽略问题。
也不要为了发现问题而制造问题。

### Dialect / 平台约束

必须依据输入中明确提供的 SQL dialect 进行判断。

不得把传统关系型数据库的优化机制机械套用于其他数据平台。

例如在 MaxCompute 场景：

- 不得默认建议“创建索引”；
- 性能分析应优先考虑：
  - 分区裁剪；
  - 扫描数据范围；
  - JOIN 规模与方式；
  - 数据倾斜；
  - 重复扫描；
  - 不必要的中间结果；
- 如果上下文不足以确认性能问题，应输出 advisory 或 uncertainty，
  不得虚构平台能力。

### action 约束

LLM 只能输出以下 action：

- advisory
- auto_fix
- context_required
- human_review

禁止输出：

- block
- ignore

BLOCK 只允许 Deterministic Guardrail 产生。

如果认为问题严重但无法由确定性规则证明，
必须使用 human_review。

### auto_fixable

不要输出 auto_fixable。
是否可以自动修复由系统根据 action=auto_fix 自动派生。

禁止编造：

- 不存在的表
- 不存在的字段
- JOIN 关系
- 指标定义
- 日期规则
- 分区值
- 业务口径

只返回符合 Schema 的 JSON object。
""".strip()


REPAIR_SYSTEM_PROMPT = """
你负责修复上一轮 SQL Review 返回结果的 JSON Contract。

上一轮已经完成 SQL Review。
本次不要重新审查 SQL，
不要新增问题，
不要删除问题，
不要改变 Issue 的业务含义。

你的唯一任务是：

- 按本次调用提供的 JSON Schema 修复结构；
- 补齐 required 字段；
- 修正错误字段名；
- 修正字段层级；
- 修正字段类型；
- 删除 Schema 不允许的多余字段。

必须严格遵守本次调用提供的 JSON Schema。

只返回 JSON object。
不要返回 Markdown code fence。
不要返回任何解释文字。
""".strip()


def build_issues_text(
    issues: list[Issue],
) -> str:

    if not issues:
        return "无确定性问题。"

    return json.dumps(
        [
            issue.to_dict()
            for issue
            in issues
        ],
        ensure_ascii=False,
        indent=2,
    )


def build_user_prompt(
    *,
    sql: str,
    file_path: str,
    guardrail_catalog_text: str,
    deterministic_issues_text: str,
    analysis_context_text: str = "",
    metadata_context_text: str = "",
    query_context: QueryContext | None = None,
) -> str:

    return f"""
请审查以下 SQL。

## 文件路径

{file_path}

## Query Context

{build_query_context_text(query_context)}

## Deterministic Guardrails

{guardrail_catalog_text}

## 已发现的确定性问题

{deterministic_issues_text}

## SQL Analysis / SQLFacts

{analysis_context_text or "未提供。"}

## Metadata Context

{metadata_context_text or "未提供。"}



## SQL

```sql
{sql}
```
## Context Authority

Query Context 中已经明确提供的业务定义、
业务筛选条件、指标口径、运行期参数和
Session Context，应作为当前任务的有效业务证据。

不要再次要求确认 Query Context
已经明确提供的信息。

Metadata Context 对以下物理事实具有权威性：

表是否存在；
字段是否存在；
字段类型；
物理分区属性。

Query Context 对以下业务事实具有权威性：

业务术语映射；
指标定义；
业务过滤条件；
当前任务时间语义；
运行参数约定；
用户已经确认的信息。

请基于以上完整上下文独立执行智能 Review，
并严格输出 JSON。
""".strip()


def build_repair_prompt(
    *,
    raw_result: dict,
    error_message: str,
    ) -> str:

    return f"""

上一轮 JSON 不符合 Contract。

Validation Error

{error_message}

Raw Result

{json.dumps(
raw_result,
ensure_ascii=False,
indent=2,
)}

请只修复 JSON 结构。
""".strip()

