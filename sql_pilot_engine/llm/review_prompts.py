
import json
from typing import Any
from sql_pilot_engine.core.models import (
    Issue,
)
from sql_pilot_engine.context.builder import (
    QueryContext,
)

from sql_pilot_engine.context.query_context_renderer import (
    render_query_context,
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
                        "missing_context": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
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
                        "missing_context",
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

### Evidence Priority / 证据优先级

审查 SQL 时，必须严格区分：

1. 用户当前任务中明确指定的条件；
2. Query Context 中已经确认的业务定义；
3. 仅在用户未明确指定时生效的默认业务规则。

优先级原则：

用户当前任务中的明确要求
>
已经确认的业务定义
>
默认值、默认统计期、默认参数。

如果用户已经明确指定日期、范围、对象、过滤条件或其他业务要求，
不得使用默认规则覆盖用户的明确要求。

例如：

用户明确要求“2026年7月”，
且 SQL 使用：

dt = '202607'

如果 Query Context 中另有：

“本期使用 dt = '${p_month_yyyymm}'”

该规则只适用于用户表达“本期”或未明确指定其他统计期的场景。

不得仅为了参数化、灵活性、可维护性等原因，
把用户已经明确指定的：

dt = '202607'

改写为：

dt = '${p_month_yyyymm}'

除非 Query Context 明确规定：
即使用户指定具体月份，也必须使用该运行参数。


### context_required 的严格使用边界

context_required 只能用于真正的“用户业务意图缺失”。

只有同时满足以下条件时，
才允许输出 action=context_required：

- 缺失的信息会实质改变 SQL 的业务语义；
- 当前 Query Context、Business Knowledge、
  Semantic Knowledge、Session Context 中尚未提供该信息；
- 该信息属于用户或业务方可以回答、选择或确认的事项；
- 不同回答会导致不同的正确 SQL。

以下情况禁止使用 context_required：

- SQL dialect 或数据库平台是否支持某个函数；
- 数据库版本、执行引擎能力、函数返回类型等技术事实；
- Physical Metadata 未提供某个物理属性；
- 分区属性、字段类型、执行计划等系统资产信息不足；
- Reviewer 自己无法确定某个技术判断；
- 性能优化是否一定生效；
- 已经在 Query Context 中明确给出的业务定义；
- 仅仅怀疑“可能还存在其他业务条件”，
  但当前业务知识已经给出了明确完整的规则；
- 为了再次确认已经确认过的信息。

如果存在实质性的技术风险或资产风险，
且当前系统无法安全证明正确性：

- 风险会影响 Trusted SQL：
  使用 human_review；
- 风险只是提示，不影响 SQL 可信性：
  使用 advisory。

不得把系统自身缺少技术证据的问题转嫁给业务用户。


### 已明确业务规则不得再次询问

如果 Query Context 已明确提供：

某业务概念 → 某字段 / 某过滤条件

例如：

高新技术企业贷款
→ is_high_tech_mfg_loan_code = '1'

则 SQL 已正确使用该条件时，
不得再提出：

“是否还有其他条件”
“是否应该同时包含其他业务类型”
“是否需要再次确认该定义”

除非当前上下文中存在另一个明确的、
与其直接冲突的权威业务规则。


### Issue 输出纪律

issues 数组只用于输出真实存在的：

- 错误；
- 风险；
- 不一致；
- 缺失信息；
- 需要修复或人工处理的问题。

不要把“检查通过”输出成 Issue。

禁止生成以下类型的 Issue：

- “聚合粒度正确”
- “过滤条件符合业务定义”
- “无数据放大风险”
- “分区裁剪有效”
- “性能良好”
- “无需修改”

如果某项检查没有发现问题，
不要输出对应 Issue。

Issue 不是审查清单的执行记录，
而是需要后续生命周期处理的问题集合。

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

### missing_context Contract

每一个 Issue 都必须返回 missing_context。

如果：

action != context_required

则：

missing_context = []

如果：

action == context_required

则 missing_context 必须至少包含一个具体项目，
用于说明继续当前任务所缺少的用户 / 业务信息。

例如：

{
  "action": "context_required",
  "missing_context": [
    "同比统计口径"
  ]
}

禁止使用模糊内容：

[
  "更多上下文",
  "相关信息",
  "请确认",
  "需要更多资料"
]

missing_context 必须具体到用户能够回答的问题。

如果缺失的是：

数据库能力、
Metadata、
SQL dialect、
执行引擎信息、
系统资产信息，

不得放入 missing_context，
也不得使用 context_required。

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

{render_query_context(query_context)}

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

Metadata Context 中明确提供的物理事实，
应作为当前任务的权威物理证据。

包括但不限于：

表存在性；
字段存在性；
字段类型；
物理分区属性。

只有 Metadata Context 明确提供了某项物理事实时，
才能基于该事实作出确定性判断。

某项物理属性未出现在 Metadata Context 中，
表示当前提供给你的证据中没有该事实。

不得根据“某项事实没有被提供”
反向推断该事实为 False、None、不存在或配置错误。

例如：

如果 Metadata Context 没有提供
Is Partitioned 或 Partition Fields，
不得据此判断该表不是分区表，
也不得仅因为缺少该事实要求业务用户确认数据库物理属性。

业务用户不负责补充数据库自身的物理元数据事实。

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

