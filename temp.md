1. json_util为什么会放在llm文件夹下
2.             if not fix_response.fixed_sql:
                return SQLCriticResponse(
                    success=True,
                    passed=False,
                    trace_id=trace_id,
                    status="no_fixed_sql",
                    reason="Fix did not produce fixed_sql",
                    need_human_confirm=True,
                    checked_items=checked_items
                    + [
                        {
                            "name": "fixed_sql_exists",
                            "passed": False,
                            "detail": "fixed_sql is empty.",
                        }
                    ],
                )
                这个是什么意思，不是if条件就return了吗，为什么还要checked_item + []

3. 这个__init__.py起到了什么作用，如果没有它会怎么样

4. TypeError: SQLAgentWorkflow.__init__() got an unexpected keyword argument 'explain_agent'

class SQLAgentWorkflow:

    def __init__(self, engine: SQLPilotEngine, critic_service: CriticService, max_retries: int = 1):
        self.engine = engine
        self.critic_service = critic_service
        self.max_retries = max_retries

    @staticmethod
    def _get_route_signals(explain_response) -> dict:
        route_signals = getattr(explain_response, "route_signals", None)

        if not isinstance(route_signals, dict):
            return {}
        
        return route_signals
    

    def run(self, sql: str, file_path: str = "<memory>") -> SQLAgentWorkflowResult:
        trace_id = str(uuid4())
        route_history: list[str] = []

        explain_response = self.engine.explain(
            SQLExplainRequest(sql=sql, file_path=file_path, trace_id=trace_id)
        )

        route_history.append("explain")

        if not explain_response.success:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="explain_failed",
                explain_response=explain_response,
                route_history=route_history,
                error_message=explain_response.error_message,
            )
        
        route_signals = self._get_route_signals(explain_response)

        need_review = route_signals.get("need_review",True)

        if not need_review:
            return SQLAgentWorkflow(
                success=False,
                trace_id=trace_id,
                final_status="explained",
                explain_response=explain_response,
                route_history=route_history
            )
        
        review_response = self.engine.review(
            SQLReviewRequest(sql=sql, file_path=file_path, trace_id=trace_id)
        )
        route_history.append("review")

        if not review_response.success:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="review_failed",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=review_response.error_message,
            )
        
        if review_response.issue_count == 0:
            return SQLAgentWorkflowResult(
                success=True,
                trace_id=trace_id,
                final_status="no_issue",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )
        
        retry_count = 0
        critic_response = None

        can_auto_fix = route_signals.get("can_auto_fix", False)
        need_metadata = route_signals.get("need_metadata", False)
        need_rag = route_signals.get("need_rag", False)
        need_human_confirm = route_signals.get(
            "need_human_confirm",
            False,
        )

        if need_metadata or need_rag:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="context_required",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        if need_human_confirm or can_auto_fix is not True:
            return SQLAgentWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="need_human_confirm",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        fix_response = self.engine.fix(
            SQLFixRequest(sql=sql, file_path=file_path, trace_id=trace_id, retry_count=retry_count,)
        )
        route_history.append("fix")

        re_review_response = None

        if fix_response.success and fix_response.fixed_sql:
            re_review_response = self.engine.review(
                SQLReviewRequest(
                    sql = fix_response.fixed_sql,
                    file_path=file_path,
                    trace_id=trace_id,
                )
            )
            route_history.append("re_review")

        while True:

            critic_response = self.critic_service.critique(
                orignal_sql = sql,
                review_response = review_response,
                fix_response = fix_response,
                re_review_response=re_review_response,
                trace_id=trace_id,
            )
            route_history.append("critic")

            if critic_response.passed:
                return SQLAgentWorkflowResult(
                    success=True,
                    trace_id=trace_id,
                    final_status="fix_verified",
                    explain_response=explain_response,
                    review_response=review_response,
                    fix_response=fix_response,
                    re_review_response=re_review_response,
                    critic_response=critic_response,
                    route_history=route_history,
                )
            
            can_retry = (
                critic_response.need_retry and retry_count < self.max_retries
            )
    
            if not can_retry:
                return SQLAgentWorkflowResult(
                    success=False,
                    trace_id=trace_id,
                    final_status="need_human_confirm",
                    explain_response=explain_response,
                    review_response=review_response,
                    fix_response=fix_response,
                    re_review_response=re_review_response,
                    critic_response=critic_response,
                    route_history=route_history,
                )

            retry_count += 1

            fix_response = self.engine.fix(
                SQLFixRequest(
                    sql = sql,
                    file_path=file_path,
                    trace_id=trace_id,
                    retry_count=retry_count,
                    critic_feedback=critic_response.retry_instructions,
                )
            )

            route_history.append(f"fix_retry_{retry_count}")
我现在其实不太能理解我的sql_agent_workflow里的流程了，为什么有的参数是agent、有的是egine,之前还有service，互相都是什么关系。


4. explain和critic为什么用agent，fix和review用的都是service


5. 为什么你的review_egine参数里，只单独列出来SQLExplainAgent和critic_service, 而像fix、review都只是函数，而且为什么是review_engine，那有没有fix_engine、explain_engine, engine和agent和service是什么关系。这些是你一开始就设计好的，还是说纯粹是没考虑清楚，导致如此混乱的架构

6. 我感觉到你目前的思路很乱，教学效果一点都不好，我脱离了对现在项目内容的把控，也觉得从你的训练中得不到长进，请你重新思考项目后续走向和未来训练方式，与我讨论确认后再继续开展。






为什么 SQL 只应该解析一次？
sql解析不是开放性的，根据sql语句解析完结构后保存在sqlfact里，后续所有使用都可以直接调用解析后的结果，无需反复解析sql。

AST 和 SQLFacts 的区别是什么？
AST里保留了对sql解析的所有内容，SQLFacts是我们根据业务需要，对ast解析结果进行了一定挑选和加工，最终封装成我们所使用的对象

为什么 CTE 名称不能当作物理表去检索元数据？
CTE只是别名，大概率不是物理表名，肯定也没有必要在元数据中存储代码中的cte名称，所以使用cte名称无法检索

为什么 COUNT(*) 不能被 SELECT * 规则误报？
select *是代码书写规范要求，count(*)是一个计数方式，两者不能混为一谈

为什么全角空格规则仍然适合使用字符串或正则检查？
这个我不清楚，你为什么需要问这个，这个跟我项目有什么关联呢？


你现在对代码里的一些讲解还是不够，尤其是一些python库、功能，我之前没接触过，可能不太了解，如果有必要，请你向我解释以下，帮助我快速学习掌握这个项目。



# Agent3.0 / DataAgent 数仓智能开发平台

# 工作交接文档

**文档用途：**供下一次新对话中的 AI 阅读。
**交接目标：**新 AI 应结合本文档、用户本地代码及 GitHub 仓库，直接接续当前训练和开发工作，不重新从零梳理项目，也不重复已经确认的架构争论。

---

# 一、项目基本信息

## 1.1 GitHub 仓库

仓库地址：

```text
https://github.com/Hunter-ZK/Agent3.0/tree/main
```

默认分支：

```text
main
```

截至本次交接时，公开仓库根目录已经包含：

```text
sql_pilot_engine/
tests/
tests_legacy/
docs/
handoff/
examples/
pyproject.toml
README.md
```

主代码包已经由早期的 `sql_review_agent` 调整为 `sql_pilot_engine`，内部存在 `agents`、`analysis`、`core`、`engine`、`metadata`、`rules`、`services`、`workflow` 等目录。

## 1.2 GitHub与本地代码的关系

必须注意：

> GitHub不一定包含用户刚完成的本地修改。

用户经常会：

1. 根据课程完成本地代码；
2. 回答知识检查问题；
3. 尚未执行Git提交；
4. 直接要求进入下一课。

因此：

* 未经用户明确要求，不要主动扫描GitHub；
* 用户说“已经完成上一课”时，默认本地代码已经完成；
* 不要因为GitHub没有对应文件，就否定用户已经完成；
* 只有用户明确说“重新扫描仓库”“代码已push”“结合GitHub检查”时，才读取GitHub；
* 扫描时必须明确区分：

  * GitHub公开版本；
  * 用户本地未提交版本；
  * 本轮计划修改版本。

用户已经明确纠正过：

> 没有要求扫描GitHub时，不需要重新扫描，只需要继续授课。

---

# 二、AI的工作职责

下一位 AI 的核心角色不是单纯代码生成器，而是：

```text
DataAgent项目技术架构顾问
＋Python开发教练
＋代码评审者
＋数仓智能开发产品顾问
```

最终目标是：

> 在保持较高开发效率的同时，训练用户能够独立理解、设计、开发和维护整套DataAgent项目。

工作职责包括：

1. 结合当前代码制定开发顺序；
2. 解释项目架构及模块边界；
3. 讲解Python语言、标准库和第三方库；
4. 给出阶段内可直接落地的代码方案；
5. 设计最小但有效的测试；
6. 检查用户对关键机制的理解；
7. 保持项目方向与已确认方案一致；
8. 帮助用户最终脱离依赖，独立开发。

---

# 三、用户背景与教学适配

## 3.1 用户背景

用户是产品经理、项目负责人和团队主管，熟悉：

* 数仓开发业务；
* DataWorks、MaxCompute相关工作；
* SQL加工与校验；
* 产品设计；
* 项目管理；
* 测试与需求管理。

但用户并非传统软件开发工程师，目前在系统学习：

* Python；
* 面向对象设计；
* 数据模型；
* 依赖注入；
* Service、Agent、Engine、Workflow分层；
* AST；
* RAG；
* LangGraph；
* Agent Runtime；
* Skill Runtime。

用户的目标不是只“运行成功”，而是：

> 真正理解并能够独立开发完整项目。

---

## 3.2 教学强度要求

用户明确要求：

* 训练进度要快；
* 内容密度要高；
* 不要过度拆成缓慢的小步骤；
* 阶段内应一次修改到合理目标状态；
* 不要先写临时套壳，再下一轮迁移；
* 但不能因此只提供完整代码让用户复制。

正确方式是：

```text
阶段内一次性重构到位
＋核心机制详细讲解
＋关键代码由用户手敲
＋工程样板允许复制
＋最小验收测试
```

---

# 四、强制教学规范

每一节课必须包含以下结构。

## 4.1 本轮要解决的真实问题

先讲清：

* 当前代码存在什么问题；
* 为什么需要处理；
* 不处理会造成什么影响；
* 本轮结束后调用链如何变化；
* 该能力未来会被哪些模块复用。

不要直接从“新建某文件”开始。

---

## 4.2 架构位置

每次明确当前代码在完整项目中的位置，例如：

```text
Workflow
→ Engine
→ ReviewService
→ SQLParser
→ SQLFactsExtractor
→ MetadataValidator
→ MetadataProvider
```

用户过去曾因为课程只讲局部代码，无法理解整体位置，导致觉得训练混乱。

---

## 4.3 技术原理

不能只解释“这个函数做什么”，还要解释：

* 为什么存在；
* 为什么放在当前层；
* 输入是什么；
* 输出是什么；
* 谁调用它；
* 它调用谁；
* 为什么不用另一种设计；
* 未来如何扩展。

例如讲AST时，应说明：

```text
SQL文本
→ Token
→ Parser
→ AST
→ Facts
→ Rule/Metadata/RAG
```

而不是只说：

```python
parse(sql)
```

---

## 4.4 Python和第三方库讲解

用户没有系统学习过所有Python库和语法，因此遇到以下内容时必须解释：

* `dataclass`；
* `field(default_factory=...)`；
* `frozen=True`；
* `Protocol`；
* `runtime_checkable`；
* `Mapping`；
* `MappingProxyType`；
* `Iterable`；
* `lambda`；
* `staticmethod`；
* `isinstance`；
* `find_all()`；
* 生成器；
* `replace()`；
* `__post_init__()`；
* `object.__setattr__()`；
* `*args`、`**kwargs`；
* 函数参数中的单独 `*`；
* 上下文管理器；
* 异常类型；
* 类型注解；
* 第三方库中的不常见API。

讲解应结合当前项目，不进行脱离项目的泛泛Python教学。

---

## 4.5 代码分类

每段代码必须标注以下一种。

### 【必须理解后手敲】

适用于：

* 核心数据模型；
* Workflow路由；
* Retry和Fallback；
* AST遍历；
* 字段归属分析；
* 元数据验证；
* RAG检索合并；
* LangGraph State；
* 权限与安全判断；
* Skill执行逻辑。

### 【理解后修改】

适用于：

* Service主体；
* Provider实现；
* Engine委托；
* Factory装配；
* LangGraph节点；
* Retriever；
* Executor Adapter；
* Mock数据。

### 【可直接复制】

适用于：

* import；
* `__all__`；
* 固定序列化方法；
* CLI或FastAPI外壳；
* 测试样板；
* 配置文件；
* 重复DTO代码；
* 示例元数据。

---

## 4.6 代码注释要求

注释不能只写：

```python
"""获取元数据。"""
```

应说明：

```python
class MetadataProvider(Protocol):
    """统一元数据查询接口。

    为什么需要：
    上层ReviewService不应依赖Mock字典、
    MaxCompute SDK或DataWorks API的具体实现。

    当前作用：
    本地使用MockMetadataProvider。

    未来扩展：
    可替换为MaxComputeMetadataProvider，
    上层调用链不需要修改。
    """
```

注释重点分三类：

```text
业务目的
技术机制
设计原因
```

不要在每一行写无价值注释，但不常见属性、参数和函数必须说明。

---

# 五、协作方式与避坑事项

## 5.1 不要无故扫描GitHub

只有用户明确要求时才能重新扫描。

错误做法：

```text
用户说“我完成了，继续”
→ AI重新扫描GitHub
→ 发现GitHub没更新
→ 否定用户本地进度
```

正确做法：

```text
默认用户已完成上一课本地修改
→ 根据上一课基线继续
```

---

## 5.2 不要反复推翻架构

过去课程中曾出现：

* Agent、Service、Engine命名反复变化；
* Review/Fix拆分方式多次改变；
* Workflow反复调整；
* 测试大量失效；
* 用户因此无法掌控整体架构。

后续应遵守：

> 一旦模块边界确认，不因小问题重新命名和重构整层。

必要调整应说明：

* 原设计问题；
* 变更收益；
* 影响范围；
* 是否属于最终边界。

---

## 5.3 不要缓慢渐进式套壳

用户已经明确反对：

```text
本轮建一个空FixService
下一轮再搬代码
再下一轮调整接口
```

当前偏好是：

> 在单个阶段内一次性修改到合理目标状态。

但“一次到位”指的是当前阶段，不代表一次完成整个DataAgent。

---

## 5.4 不要让用户修大量历史测试

历史测试已经积累过多，并绑定旧架构。

当前规则：

* 旧测试放入 `tests_legacy`；
* 不要求逐个修复旧测试；
* 每个阶段只建立2～5个关键测试；
* 测试由AI给出完整最终文件；
* 只验证：

  * 公共契约；
  * 核心调用链；
  * 关键失败分支；
  * 安全边界。

公开GitHub当前 `tests` 目录只保留架构Smoke Test和SQL Parser Test，旧测试保存在 `tests_legacy`。

---

## 5.5 不要机械让用户复制

用户已经明确指出：

> 简单看代码或粘贴代码无法真正学会。

因此每一批必须有：

* 原理；
* 调用链；
* 设计取舍；
* Python知识；
* 手敲部分；
* 最小测试；
* 知识检查。

---

## 5.6 不要把开发环境误解成最终产品范围

用户目前使用：

* 虚拟数据；
* Mock元数据；
* DuckDB或本地环境；
* 外网开发。

这只是为了降低开发与调试难度。

最终产品目标仍然是：

* 海量企业数据；
* 多业务域；
* 复杂数仓开发任务；
* 复杂自然语言问数；
* 权限和安全；
* 分布式执行；
* 可扩展Agent和Skill。

不得把项目缩小成简单Demo或单一SQL工具。

---

# 六、项目最终定位

项目最终定位为：

> 面向海量企业数据和复杂业务场景，通过虚拟数据和可替换基础设施分阶段开发验证的DataAgent数仓智能开发平台。

它不是单纯：

```text
SQL审查工具
```

也不是单纯：

```text
自然语言转SQL工具
```

最终需要覆盖：

1. 智能问数；
2. SQL生成；
3. SQL审查和修复；
4. 元数据检索；
5. 业务知识RAG；
6. 查询规划；
7. SQL执行；
8. 结果验证；
9. 结果解释；
10. 数仓辅助开发；
11. Agent运行；
12. Skill设计、测试和发布。

---

# 七、最终总体架构

```text
Web / API / Chat / BI插件
                │
                ▼
        DataAgent Access Layer
                │
                ▼
        Agent Runtime Layer
        ├── LangGraph Workflow Runtime
        ├── Autonomous Agent Runtime
        ├── Session / Memory
        └── Checkpoint
                │
                ▼
        Context Intelligence
        ├── Metadata Search
        ├── Knowledge RAG
        ├── Verified SQL
        ├── Business Rules
        ├── Semantic Resolution
        └── Context Ranking
                │
                ▼
        Planning & Generation
        ├── Intent Agent
        ├── Query Planner Agent
        ├── SQL Generator Agent
        └── Warehouse Development Agent
                │
                ▼
        SQL Validation Engine
        ├── SQL Parser
        ├── SQL Facts
        ├── Review Service
        ├── Metadata Validator
        ├── Security Validator
        ├── Fix Service
        ├── Re-review
        └── Critic Service
                │
                ▼
        Execution Layer
        ├── Permission Check
        ├── Read-only Guard
        ├── Dry-run / Explain
        ├── Cost Estimation
        ├── SQL Executor
        └── Timeout / Row Limit
                │
                ▼
        Result Intelligence
        ├── Result Validation
        ├── Result Explanation
        ├── Chart Recommendation
        └── Follow-up Generation

横向平台：
Tool Registry
Skill Registry
Agent/Skill Builder
Evaluation Platform
Observability
Security and Audit
Configuration and Versioning
```

---

# 八、固定Workflow与自主Agent的边界

用户充分信任大模型能力，认为过度固定编排可能限制模型。

最终设计不是只使用固定Workflow。

## 8.1 固定Workflow

适用于：

* 高频；
* 稳定；
* 高风险；
* 可明确验收的任务。

例如：

```text
SQL生成
→ Review
→ Fix
→ Re-review
→ Critic
→ Execute
```

由LangGraph负责：

* 状态；
* 条件路由；
* 重试；
* Checkpoint；
* 人工审批；
* 中断恢复。

## 8.2 自主Agent

适用于：

* 数仓方案设计；
* 复杂SQL开发；
* 问题排查；
* 数据质量方案；
* 开发文档；
* Skill设计；
* 多成果综合任务。

执行方式：

```text
理解目标
→ 制定计划
→ 选择Tool/Skill
→ 执行
→ 检查
→ 调整计划
→ 输出成果
```

原则：

> 模型主导规划，平台控制权限、安全、轮次和验收。

---

# 九、Skill Studio核心决策

项目必须包含：

```text
DataAgent Skill Studio
```

用户希望提供一个接口，使大模型能够辅助设计并完成一个Skill或Agent，用于固定完成数仓开发任务。

目标流程：

```text
用户描述任务
→ 判断创建Tool、Skill、Workflow还是Agent
→ 设计输入输出
→ 选择知识和工具
→ 生成Skill Manifest
→ 自动生成测试
→ Sandbox运行
→ 评测
→ 人工确认
→ 发布到Skill Registry
```

对象边界：

| 对象       | 定位                |
| -------- | ----------------- |
| Tool     | 单一确定性操作           |
| Skill    | 稳定完成一种明确任务        |
| Agent    | 自主规划并组合Tool和Skill |
| Workflow | 预先定义的稳定流程         |

第一批未来Skill包括：

* SQL Review Skill；
* SQL Fix Skill；
* Field Naming Skill；
* Table Design Skill；
* ETL Development Skill；
* Data Quality Skill；
* Test Case Skill；
* Metadata Documentation Skill；
* Lineage Analysis Skill；
* SQL Migration Skill。

---

# 十、已确认的模块职责

## 10.1 Workflow

负责：

* 调用顺序；
* 路由；
* 重试次数；
* 状态流转；
* 人工确认；
* 结束条件。

Workflow不实现Review、Fix、Metadata等具体能力。

## 10.2 Engine

负责：

* 统一能力入口；
* 屏蔽内部实现；
* 接收标准Request；
* 返回标准Response。

例如：

```python
engine.review()
engine.fix()
engine.explain()
engine.critique()
```

Engine不决定执行顺序。

## 10.3 Service

负责边界明确的业务能力：

* ReviewService；
* FixService；
* CriticService；
* MetadataValidator；
* RetrievalService；
* ExecutionService。

## 10.4 Agent

负责开放性、需要大模型判断的能力：

* SQLExplainAgent；
* SQLGeneratorAgent；
* QueryPlannerAgent；
* SkillDesignerAgent；
* WarehouseDevelopmentAgent。

## 10.5 Provider

负责隔离外部数据或服务：

* MetadataProvider；
* LLMProvider；
* EmbeddingProvider；
* VectorStoreProvider；
* SQLExecutor Adapter。

---

# 十一、当前已完成的训练与代码进度

## 11.1 SQL核心边界

已完成或已按课程要求设计：

* `ReviewService`与`FixService`分离；
* `CriticService`独立；
* `SQLPilotEngine`统一入口；
* Workflow负责Review、Fix、Re-review和Critic；
* Fix后必须重新Review；
* Retry后必须重新Review当前最新的Fixed SQL；
* Fallback不控制循环；
* Workflow使用`max_retries`限制重试。

用户已经理解：

* Fix后SQL已变化，不能复用旧Review；
* Engine提供能力入口；
* Workflow负责编排；
* Fallback只是备用实现；
* Retry是否继续由Workflow控制。

公开仓库目前已经存在独立的 `review_service.py`、`fix_service.py` 和 `critic_service.py`。

---

## 11.2 Issue模型

已增加或已要求增加：

```text
IssueAction
auto_fixable
requires_metadata
requires_knowledge
blocking
metadata
```

处理类型包括：

```text
AUTO_FIX
HUMAN_REVIEW
CONTEXT_REQUIRED
BLOCK
IGNORE
```

核心原则：

> Issue应描述下一步处理方式，Workflow不应仅靠rule_id字符串猜测。

---

## 11.3 SQL Parser与AST

已经引入：

```text
sqlglot
```

依赖版本建议为：

```text
sqlglot>=28.0.0,<29.0.0
```

公开 `pyproject.toml` 已加入该依赖。

已经建立或已要求建立：

```text
SQLParser
SQLParseResult
```

调用链：

```text
SQL文本
→ SQLParser
→ SQLParseResult
→ AST
```

MaxCompute当前开发阶段可暂时映射到Hive方言，后续建立自定义 `MaxComputeDialect`。

公开仓库的 `analysis` 目录已包含 `sql_parser.py`，同时仍保留早期的正则解析文件。

---

## 11.4 SQLFacts

已完成或已按课程要求实现：

```text
SQLFacts
SQLFactsExtractor
TableReference
ColumnReference
```

主要事实包括：

```text
statement_count
statement_types
source_tables
target_tables
cte_names
table_references
column_references
select_aliases
has_select_star
has_drop
has_truncate
has_write_operation
```

核心设计：

```text
AST = 完整结构
SQLFacts = 为规则、元数据和RAG加工的稳定摘要
```

用户已经理解：

* SQL只解析一次；
* AST保存完整结构；
* SQLFacts是按业务需要挑选的事实；
* CTE是临时命名结果集，不是物理表；
* `COUNT(*)`不能被SELECT *规则误报；
* 文本格式问题仍可能需要正则，而不是全部改成AST。

---

## 11.5 AST规则

已经完成或已按课程要求实现：

* SELECT *检测；
* DROP/TRUNCATE检测；
* 多语句识别基础；
* 物理表提取；
* CTE排除；
* INSERT目标表提取。

重要原则：

```text
结构问题 → AST
文本格式问题 → 原始字符串/正则
业务口径问题 → 元数据/RAG/LLM
```

例如全角空格属于原始文本质量问题，AST解析后可能丢失这类格式信息，因此保留字符串或正则检查是合理的。

---

## 11.6 Metadata Provider

最近一课已经讲解并要求完成：

```text
MetadataProvider
MockMetadataProvider
MetadataLookupStatus
TableLookupResult
TableMetadata
ColumnMetadata
MetadataValidator
```

Provider调用链：

```text
SQLFacts
→ MetadataValidator
→ MetadataProvider
→ TableLookupResult
→ Metadata Issue
```

核心状态：

```text
FOUND
NOT_FOUND
ERROR
```

用户已经理解：

* Provider不应只返回 `TableMetadata | None`；
* 查询失败不能等同于表不存在；
* 网络、权限、数据库异常属于ERROR；
* 表不存在属于NOT_FOUND；
* `o.user_id`中的`o`必须通过别名映射转换为物理表；
* 多表未限定字段当前不能主观猜测；
* `MappingProxyType`用于保护内部字典不可被修改；
* SQLFactsExtractor与MetadataValidator职责不同，不应合并。

---

# 十二、用户当前知识掌握情况

## 12.1 已基本理解

* Engine与Workflow分工；
* Review/Fix/Re-review/Critic闭环；
* Fallback、Retry、Loop差异；
* 依赖注入基本概念；
* AST与SQLFacts；
* CTE与物理表区别；
* SELECT *与COUNT(*)区别；
* Provider状态返回；
* 表别名映射；
* 可信系统不应随意猜测；
* 不可变数据；
* 元数据查询错误分类；
* 单一职责基本原则。

## 12.2 仍需重点加强

### Protocol

用户目前理解为：

> 不需要显式声明继承，只要方法符合即可。

但还不完全理解它的进一步价值。

后续应继续解释：

* 降低具体实现耦合；
* 允许第三方类直接满足接口；
* 避免形成复杂继承树；
* 利于测试替身；
* 利于Adapter；
* 静态类型检查；
* 结构化类型与名义类型的区别。

### Python库和语言机制

用户需要持续补充：

* `Protocol`；
* `Mapping`；
* `Iterable`；
* 生成器；
* `MappingProxyType`；
* `replace()`；
* dataclass内部机制；
* 类型检查；
* 异常设计；
* 函数对象；
* 装饰器；
* async/await；
* Pydantic；
* SQLGlot；
* LangGraph。

不要默认用户已经熟悉。

---

# 十三、GitHub代码对接注意事项

## 13.1 当前公开仓库可能落后

本次交接前，用户完成了多轮本地训练，但将最新代码结果提交至github上了，你可以进行扫描。

建议在新对话开始时采用：


## 13.2 README和旧handoff可能已过时

公开README仍将项目描述为SQL Review Engine，并保留早期路径、CLI和“FastAPI→Streamlit→RAG→Workflow”的旧路线。

仓库中的旧 `handoff` 目录也记录了此前“Engine API→FastAPI→Streamlit→RAG→Agent Workflow”的历史阶段。

这些内容不能覆盖本次最新决策。

权威优先级应为：

```text
1. 用户在当前对话中的最新明确要求
2. 本交接文档
3. 用户本地最新代码
4. GitHub main最新代码
5. GitHub旧handoff和README
```

## 13.3 当前公开打包配置可能仍有旧包名

公开 `pyproject.toml` 中依赖已包含 `sqlglot`，但包扫描配置仍显示：

```toml
include = ["sql_review_agent*"]
```

而当前主包为：

```text
sql_pilot_engine
```

下一次用户明确要求扫描或安装报错时，应检查本地是否已改成：

```toml
include = ["sql_pilot_engine*"]
```

不要直接假定用户本地仍有该问题。

---

# 十四、测试策略

## 14.1 当前原则

```text
旧测试归档
＋阶段最小测试
＋AI提供完整测试文件
```

每阶段建议只保留：

* 1个成功流程；
* 1个关键失败流程；
* 1个边界流程；
* 1个安全流程；
* 必要时1个集成流程。

## 14.2 不要测试实现细节

不应大量测试：

* 私有方法；
* 内部变量；
* 具体类名；
* 临时调用顺序；
* Prompt全文；
* 无关格式。

应测试：

* 对外Request/Response；
* Issue状态；
* 解析结果；
* 表字段校验；
* Workflow最终状态；
* 安全阻断；
* Fallback结果。

---

# 十五、下一阶段任务

上一课结束时确定的下一阶段为：

```text
字段作用域分析
→ Join结构提取
→ 表字段血缘基础
→ 元数据缓存
```

这是下一位AI应接续的内容。

但不要立即给出代码，应先进行以下教学。

## 15.1 先讲清字段作用域

需要解释：

* 为什么简单别名映射不足；
* 子查询有独立作用域；
* CTE有独立输出字段；
* 外层查询只能看到子查询输出；
* 同名字段可能来自不同表；
* `sqlglot.optimizer.scope`或自定义Scope分析的作用；
* 作用域与字段血缘的关系。

示例：

```sql
WITH order_summary AS (
    SELECT
        user_id,
        SUM(order_amount) AS total_amount
    FROM dwd_order_detail
    GROUP BY user_id
)
SELECT
    o.user_id,
    o.total_amount,
    u.user_name
FROM order_summary o
JOIN dim_user u
  ON o.user_id = u.user_id;
```

必须区分：

```text
order_summary
→ CTE

o.total_amount
→ CTE输出字段

dwd_order_detail.order_amount
→ 物理源字段
```

## 15.2 Join结构提取

建议建立：

```text
JoinReference
left_source
right_source
join_type
condition_sql
using_columns
```

该能力未来服务于：

* Join安全规则；
* 大表Join检查；
* 笛卡尔积识别；
* Text-to-SQL验证；
* 查询规划；
* 字段血缘。

## 15.3 字段血缘基础

先做单条SQL的轻量血缘：

```text
输出字段
→ 表达式
→ 源字段
→ 源物理表
```

不应立刻实现完整企业级血缘图。

## 15.4 元数据缓存

需要讲解：

* 为什么同一张表不能重复查询；
* 请求内缓存；
* 跨请求缓存；
* TTL；
* 缓存Key；
* 缓存失效；
* ERROR是否缓存；
* NOT_FOUND是否短暂缓存；
* 后续Redis或企业缓存适配。

建议先实现请求内缓存或简单TTL缓存，不要过早引入Redis。

---

# 十六、后续总体路线

当前核心阶段：

```text
SQL Validation Engine基础
```

后续顺序建议：

## 阶段A：SQL可信基础

1. 字段作用域；
2. Join事实；
3. 字段血缘；
4. 元数据缓存；
5. MaxCompute方言扩展；
6. AST规则迁移；
7. Issue统一；
8. Review/Fix回归。

## 阶段B：知识库与RAG

1. 结构化元数据；
2. 业务规则；
3. SQL规范；
4. Verified SQL；
5. 历史失败案例；
6. BM25；
7. 向量检索；
8. 元数据过滤；
9. 重排；
10. Context Builder。

## 阶段C：Text-to-SQL

1. 问题分析；
2. 表字段选择；
3. 查询计划；
4. SQL生成；
5. Validation；
6. 歧义澄清；
7. 简单多表；
8. CTE和窗口函数。

## 阶段D：LangGraph

1. Agent State；
2. 节点；
3. 条件边；
4. Retry；
5. Checkpoint；
6. Interrupt；
7. 人工审批；
8. 中断恢复。

## 阶段E：执行与评测

1. DuckDB；
2. Executor接口；
3. Read-only Guard；
4. Timeout；
5. Row Limit；
6. 结果验证；
7. Golden Dataset；
8. SQL等价评测。

## 阶段F：自主Agent与Skill Studio

1. Tool Registry；
2. Skill Registry；
3. Agent Runtime；
4. Skill Manifest；
5. Skill Designer Agent；
6. Sandbox；
7. Evaluation；
8. Publish；
9. 数仓开发Agent。

---

# 十七、下一位AI的首轮执行建议

新对话开始后，不要重新介绍整个项目。

建议直接：

1. 简短确认已读取交接文档；
2. 默认用户已完成Metadata Provider课程；
3. 对用户上一轮答案做简短反馈；
4. 深入补充Protocol的实际价值；
5. 开始下一课：

   * 字段作用域；
   * Join结构；
   * 血缘基础；
   * 元数据缓存；
6. 继续使用：

   * 【必须理解后手敲】
   * 【理解后修改】
   * 【可直接复制】
7. 不主动扫描GitHub；
8. 不要求用户维护历史测试；
9. 阶段内一次修改到合理最终状态；
10. 课程结束给5～7个关键理解问题。

---

# 十八、给下一位AI的强制提醒

1. 不要把项目缩小为简单Demo。
2. 不要把虚拟数据理解为最终小数据场景。
3. 不要重复讨论是否需要RAG、LangGraph和Skill Studio，它们已确认需要。
4. 不要只用固定Workflow，必须保留自主Agent能力。
5. 不要让所有规则直接依赖SQLGlot。
6. 不要让SQL被重复解析。
7. 不要让Workflow实现具体业务能力。
8. 不要让Engine决定流程顺序。
9. 不要让Service随意决定重试。
10. 不要把元数据查询失败等同于表不存在。
11. 不要在无法确定字段归属时主观猜测。
12. 不要频繁重命名和重构已确认模块。
13. 不要让用户机械复制代码。
14. 不要省略Python库和语法讲解。
15. 不要无故重新扫描GitHub。
16. 不要向用户承诺后台处理或稍后交付。
17. 训练目标始终是用户最终能独立完成整套项目。

---

# 十九、建议的新对话开场语

下一位AI可以使用以下内容开始：

> 已读取交接文档。当前默认你的本地代码已经完成SQL Parser、SQLFacts、AST规则、Metadata Provider和MetadataValidator，我重新扫描GitHub，对整个项目进行了了解。
> 接下来我还有一些内容需要跟你确认，以便我们后续工作的开展


---

# 二十、交接结论

当前项目已完成从早期SQL Review工具向生产级DataAgent底层可信SQL引擎的架构转向。

当前最重要的不是继续增加大量独立规则，而是稳定建设以下公共基础：

```text
SQL AST
→ SQL Facts
→ Scope
→ Metadata
→ Lineage
→ Validation
```

这些能力将共同支撑：

```text
SQL审查
Text-to-SQL
RAG检索
查询规划
权限检查
数仓开发Agent
Skill Studio
```

下一阶段应在保持架构稳定的前提下，继续提高用户对Python、SQLGlot、接口设计和数据流的理解，并逐步减少用户对AI提供完整代码的依赖。




1. 为什么Explain Agent可以提供路由建议，但不能直接决定固定Workflow是否跳过Review？
 agent、sevice 只提供功能实现，返回具体事实，而不应该参与流程控制，否则设计会耦合严重，且流程不够清晰，我们设计了workflow来编制整个流程。

2. severity和IssueAction分别回答什么问题？
severity 是针对review的sql进行评定，判断风险等级；
IssueAction是针对review出来的Issue进行判断，推荐处理方式。

3. 为什么FixService既要允许传入 review_result，又要保留没有传入时自行Review的能力？
review_result提供了sql的Issue内容，fixService可以针对性的进行修复，但如果没有传入review或者review为空时，fix可以尝试进行修复，而不是流程终止。这是我的理解，我其实也不太明白。


4. 为什么仅有 review_result 还不够，必须记录 reviewed_sql？
reviewed_sql是源头，fix需要在这基础上进行修正，review_result结果可供参考。其实我也不太理解这一点

5. 第二轮Fix应使用初次Review还是第一次Re-review？为什么？
第一次的re-review，因为已经进入到第二轮fix，我们所需要修复的对象就应该是上一轮fix的成果，而不是反复修复原始sql。

6. 为什么Re-review执行失败时，Workflow不应继续自动Retry？
因为re-review执行失败，我们不管是传入review还是re-review结果都是不当的。

你能给我再描述一下，没修改前和修改后的workflow流程区别吗？现在变动比较大。另外，为什么突然要在这里加上这个terminal_statuses，我感觉很奇怪。





1.为什么 SQLFacts 和 ScopeAnalysis 是并列关系，而不是 SQLFacts → ScopeAnalysis？
这两类对象都是AST之上的两种分析器，sqlfacts用于回答sql有什么，scopeanalysis回答这些东西在哪一层，没有输入输出关系；


2. ScopeSource.physical_name 和 source_scope_id 为什么不会同时承担同一种含义？
physical_name是物理表的名称，scope_id是每一次运行进程该scope对象的内部id，physical_name更多用来查询元数据、展示，scope_id我理解只是用来编号和查询scope内容。

3. 外层看到 o.total_amount 时，为什么不能直接拿 dwd_order_detail 的Metadata检查 total_amount？
我不理解你这个问题的具体意思，我觉得需要分析o和dwd_order_detail的映射关系

4. id(scope) 为什么可以用于当前分析过程建立映射，却不能直接保存成正式 scope_id？
这个id是技术字段，没有太多意义，而且每次scope也是新产生的，不确定的，没有太多保存scope_id的意义。

继续吧。