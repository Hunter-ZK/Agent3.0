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






1. 为什么 SQLAnalysisAdapter 应该放在 analysis，而不是 services？
SQLAnalysisAdapter产出SQL结构事实，service用这些事实判断SQL是否有问题

2.为什么 SQLAnalysisResult.facts 必须允许为 None？
这个我不清楚

3. ReviewService 改成只依赖 SQLAnalysisAdapter 后，具体降低了什么耦合？
降低了对SQL分析实现细节和功能装配的耦合，

4.如果半年后从 SQLGlot 换成别的SQL解析库，哪些模块理论上应该保持不变？
sqlanalysisadapter保持不变，修改parse_result、facts、scope、lineage的具体实现



<<<<<<< Updated upstream
# Agent3.0 / DataAgent 工作交接文档

## 一、文档用途
=======





Agent3.0 / DataAgent 工作交接文档

一、文档用途
>>>>>>> Stashed changes

本文档用于将当前 Agent3.0 / DataAgent 项目的开发、教学、架构设计和进度管理工作完整交接给下一次新开启对话中的 AI。

新 AI 阅读本文档后，应结合 GitHub 仓库：

<<<<<<< Updated upstream
`https://github.com/Hunter-ZK/Agent3.0`

直接接续当前开发与训练工作。

**不要从零重新设计项目，不要重复已经解决的架构争论，也不要仅根据README判断真实进度。**

新对话第一次接续时，可以进行一次 GitHub `main` 代码级扫描，以确认本文档与最新代码是否一致。

完成首次校准后，除非用户明确要求：

> 默认用户已经完成上一轮对话要求的代码修改，不要每轮重新扫描GitHub。

---

# 二、用户背景与项目目标
=======
"https://github.com/Hunter-ZK/Agent3.0"

直接接续当前开发与训练工作。

不要从零重新设计项目，不要重复已经解决的架构争论，也不要仅根据README判断真实进度。

新对话第一次接续时，可以进行一次 GitHub "main" 代码级扫描，以确认本文档与最新代码是否一致。

完成首次校准后，除非用户明确要求：

«默认用户已经完成上一轮对话要求的代码修改，不要每轮重新扫描GitHub。»

---

二、用户背景与项目目标
>>>>>>> Stashed changes

用户不是传统软件工程师，而是具有较强数仓、SQL、DataWorks、MaxCompute、产品设计和项目管理背景的产品/项目负责人。

用户正在亲自开发 Agent3.0，目标不是简单获得一个AI生成的代码项目，而是：

<<<<<<< Updated upstream
> **通过真实项目开发，最终具备独立理解、设计、修改、维护和继续开发完整DataAgent的能力。**
=======
«通过真实项目开发，最终具备独立理解、设计、修改、维护和继续开发完整DataAgent的能力。»
>>>>>>> Stashed changes

因此开发必须同时服务两个目标：

1. 做出真实可运行的 Agent3.0 / DataAgent。
2. 培养用户自己的技术和系统设计能力。

禁止采用：

<<<<<<< Updated upstream
> AI一次性生成大量代码 → 用户机械复制 → 项目虽然能跑但用户不知道为什么。

---

# 三、主开发AI的职责
=======
«AI一次性生成大量代码 → 用户机械复制 → 项目虽然能跑但用户不知道为什么。»

---

三、主开发AI的职责
>>>>>>> Stashed changes

主开发窗口承担：

1. 项目总体架构设计。
2. 真实代码开发指导。
3. 模块边界设计。
4. 具体文件和修改位置说明。
5. Stage Gate设计。
6. Bug分析和重构。
7. 代码开发过程中同步讲解：
<<<<<<< Updated upstream

   * 为什么要做；
   * 位于架构哪层；
   * 输入输出是什么；
   * 谁调用谁；
   * 为什么这样设计；
   * 替代方案是什么；
   * 当前实现有哪些刻意保留的限制。

主开发AI**不负责进行问答考试**。

用户已经明确：

> 主窗口不要持续出题。
> 问答、知识诊断和复习由另一个专门的学习窗口负责。

因此主窗口只需：

> **高密度推进工作 + 高质量解释。**

“提高学习密度”不是多出题，而是：

> 每轮推进更多实质性项目工作，同时把关键技术讲透。

---

# 四、另外两个辅助AI角色

整个项目建议保持三个窗口分工。

## 1. 主开发与训练窗口

即当前角色。

负责：

* 架构；
* 开发；
* 重构；
* 集成；
* Stage Gate；
* 技术讲解。

不负责知识考试。

---

## 2. 学习巩固教练

负责：

* 扫描当前项目；
* 讲解架构；
* 代码阅读；
* 问答；
* 知识诊断；
* 项目复盘；
* 维护用户的能力掌握画像。

主要知识等级：

### A【必须独立掌握】

用户最终应独立设计或修改：

* Agent架构分层；
* Workflow；
* State；
* Planning；
* Context Builder；
* RAG流程；
* Provider；
* Execution安全；
* Tool / Skill；
* Evaluation。

### B【必须理解】

用户需要能够读懂、调用、调试，但不用重写成熟算法：

* SQLGlot AST；
* Scope；
* Lineage；
* LangGraph API；
* Qdrant；
* DuckDB等。

### C【知道即可】

* 成熟第三方库底层算法；
* 大量样板代码；
* 低价值实现细节。

---

## 3. 独立项目进展监督师

监督AI必须以GitHub真实代码为准。

不得因为用户口头说：

> “已经完成。”

就直接判定项目通过。

监督时检查：

* 最新Commit；
* 新增和删除文件；
* 核心源码；
* tests；
* Demo；
* pyproject依赖；
* 真实调用链；
* 文件是否只是空壳；
* 是否真正被上层调用。

完成状态必须区分：

### 【已完成】

代码 + 测试 + 调用链 + Stage Gate证据均存在。

### 【部分完成】

已有实现，但尚缺测试、集成或Demo。

### 【未完成】

只有设计、讨论、空文件或未接入代码。

但注意：

> **主开发窗口默认不每轮扫描GitHub。**

两种角色不要混淆。

---

# 五、用户偏好的开发教学方式

这是后续必须长期遵守的核心规则。

## 1. 每个阶段先说明架构位置

不要直接开始：

> 新建A.py、新建B.py。

先告诉用户：

```text
=======
   - 为什么要做；
   - 位于架构哪层；
   - 输入输出是什么；
   - 谁调用谁；
   - 为什么这样设计；
   - 替代方案是什么；
   - 当前实现有哪些刻意保留的限制。

主开发AI不负责进行问答考试。

用户已经明确：

«主窗口不要持续出题。
问答、知识诊断和复习由另一个专门的学习窗口负责。»

因此主窗口只需：

«高密度推进工作 + 高质量解释。»

“提高学习密度”不是多出题，而是：

«每轮推进更多实质性项目工作，同时把关键技术讲透。»


---

五、用户偏好的开发教学方式

这是后续必须长期遵守的核心规则。

1. 每个阶段先说明架构位置

不要直接开始：

«新建A.py、新建B.py。»

先告诉用户：

>>>>>>> Stashed changes
整个DataAgent在哪里
↓
当前阶段在哪里
↓
前面有什么
↓
当前能力为谁服务
↓
下一步是什么
<<<<<<< Updated upstream
```
=======
>>>>>>> Stashed changes

用户曾因为项目文件和模块快速增加而出现明显失控感。

因此后续必须持续维护“项目地图”。

---

<<<<<<< Updated upstream
## 2. 一个阶段只引入一个主要新能力

曾经出现过一次节奏过快：

```text
=======
2. 一个阶段只引入一个主要新能力

曾经出现过一次节奏过快：

>>>>>>> Stashed changes
RAG
+ Vector DB
+ Text-to-SQL
+ LangGraph
+ Evaluation
<<<<<<< Updated upstream
```
=======
>>>>>>> Stashed changes

连续堆叠。

用户明确反馈：

<<<<<<< Updated upstream
> 进度太快，已经有点接受不良。

因此后来冻结新原则：

> **一个阶段只引入一个主要架构概念，但该阶段内部可以一次把工作做完整。**

例如：

```text
先把Text-to-SQL普通Python链跑通
↓
再学LangGraph
```
=======
«进度太快，已经有点接受不良。»

因此后来冻结新原则：

«一个阶段只引入一个主要架构概念，但该阶段内部可以一次把工作做完整。»

例如：

先把Text-to-SQL普通Python链跑通
↓
再学LangGraph
>>>>>>> Stashed changes

而不是同时第一次学习Planner、Generator、State、Node、Edge。

---

<<<<<<< Updated upstream
## 3. 保持高工作密度，但不要碎片化

用户不喜欢：

* 一轮只改3行；
* 每次只讲一个小Python语法；
* 一直停留在局部；
* 工作进展过慢。

正确方式：

```text
=======
3. 保持高工作密度，但不要碎片化

用户不喜欢：

- 一轮只改3行；
- 每次只讲一个小Python语法；
- 一直停留在局部；
- 工作进展过慢。

正确方式：

>>>>>>> Stashed changes
一轮完成一个小Stage
+
同步讲解几个核心技术点
+
测试
+
Demo
<<<<<<< Updated upstream
```

---

## 4. 代码修改分类

长期采用：

### 【必须理解后手敲】

核心架构和领域代码，例如：

* DTO；
* Protocol；
* Workflow；
* State；
* Planner；
* Context；
* 安全判断；
* Agent编排。

### 【理解后修改】

* Adapter；
* Provider；
* Service；
* Prompt；
* Integration Glue。

### 【可直接复制】

* 测试；
* Demo；
* 配置；
* 重复DTO；
* Boilerplate。

---

## 5. 小修改给位置，不整文件替换
=======

---

4. 代码修改分类

长期采用：

【必须理解后手敲】

核心架构和领域代码，例如：

- DTO；
- Protocol；
- Workflow；
- State；
- Planner；
- Context；
- 安全判断；
- Agent编排。

【理解后修改】

- Adapter；
- Provider；
- Service；
- Prompt；
- Integration Glue。

【可直接复制】

- 测试；
- Demo；
- 配置；
- 重复DTO；
- Boilerplate。

---

5. 小修改给位置，不整文件替换
>>>>>>> Stashed changes

如果只是局部修改：

应明确：

<<<<<<< Updated upstream
```text
=======
>>>>>>> Stashed changes
文件：
xxx.py

找到：
xxx

改成：
xxx
<<<<<<< Updated upstream
```
=======
>>>>>>> Stashed changes

不要把整个项目重新打包。

只有发生大规模重构时才考虑完整文件。

---

<<<<<<< Updated upstream
# 六、冻结的V1产品边界

当前V1只保留四项核心成果：

## 1. 可信SQL

```text
=======
六、冻结的V1产品边界

当前V1只保留四项核心成果：

1. 可信SQL

>>>>>>> Stashed changes
SQL
→ Analysis
→ Review
→ Fix
→ Re-review
→ Critic
→ Trusted SQL
<<<<<<< Updated upstream
```

## 2. Text-to-SQL智能问数

```text
=======

2. Text-to-SQL智能问数

>>>>>>> Stashed changes
自然语言
→ Context
→ Plan
→ SQL Generation
→ Validation
→ Trusted SQL
<<<<<<< Updated upstream
```

## 3. 窄版数仓开发

后续：

```text
=======

3. 窄版数仓开发

后续：

>>>>>>> Stashed changes
自然语言开发需求
→ Dev Plan
→ DDL
→ ETL
→ SQL Validation
<<<<<<< Updated upstream
```
=======
>>>>>>> Stashed changes

只针对简单单目标表开发。

暂时不扩展成完整企业级数仓开发平台。

<<<<<<< Updated upstream
## 4. Agent / Skill / Evaluation基础能力

后续包括：

* LangGraph；
* Tool Registry；
* Skill Registry；
* Golden Dataset；
* Evaluation；
* Trace。

---

# 七、冻结的总体架构

```text
=======
4. Agent / Skill / Evaluation基础能力

后续包括：

- LangGraph；
- Tool Registry；
- Skill Registry；
- Golden Dataset；
- Evaluation；
- Trace。

---

七、冻结的总体架构

>>>>>>> Stashed changes
User
 ↓
Agent Runtime
 ↓
Planning
 ↓
Context Intelligence
 ↓
Generation
 ↓
SQL Validation
 ↓
Execution
 ↓
Result
<<<<<<< Updated upstream
```

横向能力：

```text
Evaluation
Tool Registry
Skill Registry
```

两个重点深挖方向：

## 核心一：Agent编排

重点：

* LangGraph；
* State；
* Node；
* Conditional Routing；
* Retry；
* HITL；
* Supervisor；
* Subgraph。

## 核心二：Context Intelligence

重点：

* Semantic Model；
* Metadata；
* RAG；
* Vector Retrieval；
* Verified SQL；
* Context Engineering；
* Schema Linking。

---

# 八、非常重要的SQL技术ADR

SQL底层明确冻结：

```text
=======

横向能力：

Evaluation
Tool Registry
Skill Registry

两个重点深挖方向：

核心一：Agent编排

重点：

- LangGraph；
- State；
- Node；
- Conditional Routing；
- Retry；
- HITL；
- Supervisor；
- Subgraph。

核心二：Context Intelligence

重点：

- Semantic Model；
- Metadata；
- RAG；
- Vector Retrieval；
- Verified SQL；
- Context Engineering；
- Schema Linking。

---

八、非常重要的SQL技术ADR

SQL底层明确冻结：

>>>>>>> Stashed changes
SQLGlot
↓
薄 SQLAnalysisAdapter
↓
Agent3.0项目DTO
<<<<<<< Updated upstream
```

禁止重新走：

```text
自己写Scope
自己写Join Analyzer
自己写Lineage Engine
```

项目曾经实现：

* `scope.py`
* `join.py`
* `lineage.py`
=======

禁止重新走：

自己写Scope
自己写Join Analyzer
自己写Lineage Engine

项目曾经实现：

- "scope.py"
- "join.py"
- "lineage.py"
>>>>>>> Stashed changes

后来确认这属于重复造SQLGlot的轮子，已经决定删除/停止正式依赖。

理由：

<<<<<<< Updated upstream
> 用户的学习目标是DataAgent，而不是SQL解析器作者。

应该：

```text
=======
«用户的学习目标是DataAgent，而不是SQL解析器作者。»

应该：

>>>>>>> Stashed changes
成熟SQL语义算法
→ SQLGlot负责

Agent3.0
→ 调用、封装、业务化
<<<<<<< Updated upstream
```

---

# 九、SQL Validation的重要已确认原则

必须长期保持。

## 1. IssueAction驱动Workflow

Workflow不要依赖：

```text
rule_id字符串判断
```

应依赖：

```text
IssueAction
```

---

## 2. Severity与Action不同

`severity`：

> 问题风险有多大。

`IssueAction`：

> 系统下一步做什么。
=======

---

九、SQL Validation的重要已确认原则

必须长期保持。

1. IssueAction驱动Workflow

Workflow不要依赖：

rule_id字符串判断

应依赖：

IssueAction

---

2. Severity与Action不同

"severity"：

«问题风险有多大。»

"IssueAction"：

«系统下一步做什么。»
>>>>>>> Stashed changes

二者不可混淆。

---

<<<<<<< Updated upstream
## 3. Fix后必须Re-review

绝对不能：

```text
Fix
→ 直接相信Fixed SQL
```

必须：

```text
=======
3. Fix后必须Re-review

绝对不能：

Fix
→ 直接相信Fixed SQL

必须：

>>>>>>> Stashed changes
Fix
↓
Re-review
↓
Critic
<<<<<<< Updated upstream
```

---

## 4. reviewed_sql是版本一致性约束

如果：

```text
Review属于SQL A
```

则不能拿来Fix：

```text
SQL B
```
=======

---

4. reviewed_sql是版本一致性约束

如果：

Review属于SQL A

则不能拿来Fix：

SQL B
>>>>>>> Stashed changes

否则必须拒绝。

---

<<<<<<< Updated upstream
## 5. Retry使用最新SQL和最新Review
=======
5. Retry使用最新SQL和最新Review
>>>>>>> Stashed changes

不能一直使用第一次Review。

正确：

<<<<<<< Updated upstream
```text
=======
>>>>>>> Stashed changes
SQL A
→ Review A
→ Fix
→ SQL B
→ Review B
→ Retry Fix必须使用Review B
<<<<<<< Updated upstream
```

---

## 6. Explain是可选增强
=======

---

6. Explain是可选增强
>>>>>>> Stashed changes

Explain失败不能阻断确定性的SQL Review能力。

---

<<<<<<< Updated upstream
## 7. Metadata状态必须区分

```text
FOUND
NOT_FOUND
ERROR
```

Provider查询失败：

```text
ERROR
```

绝不能当成：

```text
NOT_FOUND
```

---

# 十、当前SQL Validation状态

当前逻辑上已完成：

```text
=======
7. Metadata状态必须区分

FOUND
NOT_FOUND
ERROR

Provider查询失败：

ERROR

绝不能当成：

NOT_FOUND

---

十、当前SQL Validation状态

当前逻辑上已完成：

>>>>>>> Stashed changes
SQLAnalysisAdapter
SQLFacts
ReviewService
RuleRegistry
MetadataValidator
FixService
Re-review
CriticService
SQLAgentWorkflow
<<<<<<< Updated upstream
```

前一阶段已经要求完成真正 E2E：

### 正常SQL

```text
SELECT
→ no_issue
```

### 危险SQL

```text
DROP
→ BLOCK
```

### 可确定自动修复SQL

```text
=======

前一阶段已经要求完成真正 E2E：

正常SQL

SELECT
→ no_issue

危险SQL

DROP
→ BLOCK

可确定自动修复SQL

>>>>>>> Stashed changes
INSERT OVERWRITE xxx
→ AUTO_FIX
→ INSERT OVERWRITE TABLE xxx
→ Re-review
→ Critic
→ fix_verified
<<<<<<< Updated upstream
```

用户已表示完成上一轮闭环工作。

因此后续默认：

# `Trusted SQL V1 = CLOSED`

除Bug外，不再继续扩展Parser、Scope、Lineage和Review规则。

---

# 十一、Context Intelligence当前状态

当前V0.1已经建设：

```text
Semantic Model
EmbeddingProvider
TokenHashEmbeddingProvider
VectorStore Protocol
QdrantVectorStore
KnowledgeRetriever
VerifiedSQLRetriever
QueryContextBuilder
```

逻辑：

```text
Business Knowledge
Verified SQL
        ↓
ContextDocument
        ↓
Embedding
        ↓
Qdrant
        ↓
Retriever
        ↓
RetrievedDocument
        ↓
QueryContext
```

---

## Semantic Model与Metadata必须区分

Metadata：

> 数据库物理上有什么。

例如：

```text
order_amount DECIMAL
```

Semantic Model：

> 业务上是什么意思。

例如：

```text
订单总金额
=
SUM(order_amount)

消费金额
订单金额
下单金额
```

这两个不能混成同一概念。

---

## RAG与Semantic Model也不是同一东西

Semantic Model：

> 确定性的业务定义。

RAG：

> 根据当前问题动态检索相关证据。

最终模型上下文是：

```text
Semantic Model
+
Dynamic Retrieved Context
```

---

# 十二、当前Embedding策略

目前开发阶段使用：

```text
TokenHashEmbeddingProvider
```

这只是为了：

* 不依赖外部API；
* 验证RAG工程链；
* 验证Qdrant；
* 验证Retriever。

不是正式语义Embedding。

后续应新增真正实现，例如：

```text
OpenAIEmbeddingProvider
BGEEmbeddingProvider
企业Embedding Service
```

但不要修改Retriever和VectorStore上层契约。

---

# 十三、Generation当前状态

Generation V0.1已经存在：

```text
QueryPlan
TextGenerationModel Protocol
QueryPlanner
SQLGenerator
Prompt Builder
GeneratedSQL
```

流程：

```text
Question
↓
QueryPlanner
↓
QueryPlan
↓
SQLGenerator
↓
GeneratedSQL
```

`QueryPlan`当前重要字段：

```text
tables
dimensions
metrics
filters
group_by
```

前一轮已要求修复：

```text
json.load(raw)
→ json.loads(raw)
```

并确保：

```text
group_by
```

不会在Planner DTO转换时丢失。

用户已经表示完成该闭环工作。

---

# 十四、当前正在进行的工作：TextToSQLService V0.1

这是当前最重要的接续点。

目标：

```text
Question
↓
Context Retrieval
↓
Semantic Context
↓
QueryPlanner
↓
SQLGenerator
↓
SQLAgentWorkflow
↓
Trusted SQL
```

当前新增：

```text
schemas/text_to_sql.py
services/text_to_sql_service.py
tests/test_text_to_sql_service.py
examples/text_to_sql_demo.py
```

产品输入：

```text
TextToSQLRequest
```

产品输出：

```text
TextToSQLResult
```

Result至少包含：

```text
question
query_plan
generated_sql
trusted_sql
success
validation_status
```

---

# 十五、Generated SQL与Trusted SQL必须严格区分

这是核心架构原则。

```text
Generated SQL
```

只是大模型候选结果。

只有经过：

```text
Review
Fix
Re-review
Critic
```

以后，才能变成：

```text
Trusted SQL
```

例如：

```text
Generator:
INSERT OVERWRITE ads_x

Validation:
INSERT OVERWRITE TABLE ads_x
```

最终：

```text
generated_sql
≠
trusted_sql
```

这个区别必须一直保留到未来API和前端层。

---

# 十六、TextToSQLService的职责

它不是新的AI算法。

它属于高层Service：

> **将已有专业能力组合成产品功能。**

依赖：

```text
SemanticModel
KnowledgeRetriever
VerifiedSQLRetriever
QueryContextBuilder
QueryPlanner
SQLGenerator
SQLAgentWorkflow
```

不应该：

* 自己实现Embedding；
* 自己直接操作Qdrant；
* 自己实现SQL Review；
* 自己调用SQLGlot；
* 自己重写Fix。

---

# 十七、当前Demo

当前要求新增：

```text
examples/text_to_sql_demo.py
```

Demo使用：

```text
Fake Planner LLM
Fake SQL LLM
```

但使用真实：

```text
Semantic Model
Qdrant
Retriever
Context Builder
Planner代码
Generator代码
SQL Validation Workflow
```

它验证的是：

```text
自然语言
→ Context
→ Plan
→ Generate
→ Validate
→ Trusted SQL
```

Demo不连接数据库。

---

# 十八、为什么现在不做Execution

用户曾明确叫停提前开发Executor。

用户认为：

> 在Text-to-SQL、RAG和Agent链路没有真正跑通前，过早开发数据库执行层不符合当前重点。

这一判断已采纳。

因此当前：

```text
Execution = 后置
```

并且目前项目阶段：

> **不要求连接真实业务数据库。**

即便后续开始Execution：

第一阶段也可以使用：

```text
DuckDB / Mock / Local Execution
```

验证闭环。

项目监督时：

> 不得把“没有连接真实业务数据库”作为当前阶段延期风险或失败条件。

---

# 十九、为什么现在也暂缓LangGraph

之前曾过快推进：

```text
RAG
→ Generation
→ LangGraph
```

导致用户明显跟不上。

因此现在调整：

```text
先普通Python跑通产品链
↓
用户真正理解
↓
再迁移到LangGraph
```

当前建议顺序：

```text
TextToSQLService V0.1
↓
真实LLM
↓
Golden Dataset
↓
Evaluation V0.1
↓
LangGraph
```

LangGraph目前不要作为“又一个新目录”提前建设空壳。

---

# 二十、为什么LangGraph仍然是后续重点

不是取消。

后续需要使用它解决普通Service逐渐难以管理的问题：

```text
State
Node
Conditional Edge
Retry
Context Retry
HITL
Checkpoint
Subgraph
Supervisor
```

未来预期主链：

```text
START
↓
retrieve
↓
plan
↓
generate
↓
validate
↓
PASS → END

Need Context
→ retrieve again

Human Review
→ interrupt

AUTO FIX
→ Validation Subgraph
```

但必须等普通Python流程清楚以后再进入。

---

# 二十一、Evaluation是后续强制能力

Evaluation不能拖到项目最后。

Text-to-SQL真实LLM接入之后，应立即建设约10～20条第一批 Golden Dataset。

至少评：

```text
Table Selection Accuracy
Column Selection Accuracy
Metric Accuracy
SQL Parse Success
Metadata Validity
Review Pass Rate
Trusted SQL Rate
```

后续Execution接入再增加：

```text
Execution Success
Result Correctness
```

应该进行：

```text
No RAG
VS
RAG
```

对照实验。

目标不是证明：

> “我们使用了RAG。”

而是证明：

> **RAG是否真的让Text-to-SQL更准确。**

---

# 二十二、未来数仓开发线边界

V1只做窄版。

例如：

```text
“基于订单明细生成用户日汇总表”
```

输出：

```text
Dev Plan
↓
DDL
↓
ETL
↓
SQL Validation
```

Dev Planning第一版只考虑：

```text
grain
fields
partition
source tables
```

不要扩展：

```text
完整企业级建模平台
Business Analysis Agent
Data Quality Agent
复杂多层数仓Pipeline
```

业务分析和简单建模概念先嵌入Dev Planner，不独立建Agent。

---

# 二十三、Skill方向

V1只需要证明：

```text
Skill Definition
Skill Registry
Skill Runtime
Skill Invocation
```

第一批实际Skill建议：

```text
SQLReviewSkill
FieldNamingSkill
DevSQLSkill
```

其中字段规范化命名：

> 做成轻量Skill。

不要独立建设：

```text
Naming Agent
```

也不要现在建设：

```text
Skill Studio UI
AI自动生成Skill平台
```

---

# 二十四、GitHub对接规则

仓库：

`https://github.com/Hunter-ZK/Agent3.0`

新AI首次接手时应：

1. 查看最新 `main` commit。
2. 查看根目录和核心package结构。
3. 查看最近修改文件。
4. 查看 tests。
5. 查看 examples。
6. 查看 `pyproject.toml`。
7. 核对本文档描述是否已经进一步推进。

不要仅查看README。

README可能滞后于代码。

---

## 特别检查“假完成”

例如：

```text
有runtime目录
```

不等于：

```text
LangGraph已经实现。
```

必须看：

```text
文件有代码吗？
代码被调用了吗？
依赖装了吗？
测试有吗？
Demo能跑吗？
```

---

# 二十五、GitHub扫描频率规则

用户已经明确：

> 后续没有明确要求，不需要主开发AI每轮扫描main。

正常开发窗口：

```text
用户说完成上一轮
→ 默认完成
→ 继续下一阶段
```

只有用户明确说：

```text
“重新扫描”
“我push了”
“结合GitHub检查”
“监督一下”
```

才重新扫描。

监督AI除外。

监督AI以真实GitHub为准。

---

# 二十六、Python版本

项目正式兼容基线已经确定：

# Python 3.14

`pyproject.toml`最终应表达：

```toml
requires-python = ">=3.14,<3.15"
```

不要重新讨论3.10或3.12是否更成熟。

这是用户已经明确确定的项目基线。

---

# 二十七、依赖管理原则

不要一次加入大量框架。

已经采用：

```text
sqlglot
qdrant-client
OpenAI相关基础依赖
```

LangGraph真正进入开发时，再加入：

```text
langgraph
```

不要为了使用LangGraph顺便引入整套：

```text
langchain
langchain-community
langchain-openai
...
```

除非有明确价值。

原则：

> 每个依赖必须对应一个真实使用能力。

---

# 二十八、项目开发中曾出现过的主要错误路线

后续必须避免。

## 错误1：自己实现SQL Scope / Join / Lineage

已经纠正。

以后：

```text
SQLGlot负责底层算法
Agent3.0负责薄Adapter和业务DTO
```

---

## 错误2：能力还没消费者就提前实现

例如：

```text
完整Lineage
复杂Executor
空LangGraph Runtime
```

以后坚持：

> 没有真实消费者，不提前建设。

---

## 错误3：文件存在就认为功能完成

必须改成：

```text
实现
+
测试
+
接入调用链
+
Demo
```

才算Stage Gate。

---

## 错误4：一次引入太多架构概念

尤其避免：

```text
Planner
Generator
RAG
LangGraph
Eval
Execution
```

同时第一次出现。

---

## 错误5：为了“架构漂亮”过度抽象

项目目标不是构建大型企业框架。

抽象必须服务：

* 变化隔离；
* 测试；
* 多实现；
* 明确边界。

否则不要加。

---

# 二十九、用户当前技术掌握情况

根据主开发过程中表现，大致：

## 已基本掌握

* Analysis与Service职责；
* Engine / Workflow / Service基础分层；
* Dependency Injection基本思想；
* Adapter基本作用；
* Provider概念；
* SQL Review整体流程；
* SQLFacts的业务价值；
* IssueAction路由思想。

## 需要继续加强

* DTO / Result对象边界；
* Optional状态与Invariant；
* 数据依赖 vs 实现耦合；
* 第三方库防腐层；
* Protocol实际价值；
* 安全重构；
* 完整调用链思维；
* 模块“实现”与产品“完成”的区别；
* Agent State；
* LangGraph；
* RAG Retrieval/Rerank；
* Evaluation。

主开发过程中应自然强化这些能力，但不要重新变成考试窗口。

---

# 三十、当前最紧接着的工作

当前正在完成：

# Text-to-SQL Vertical Slice V0.1

需要确认：

```text
tests/test_text_to_sql_service.py
```

通过。

然后运行：

```text
python -m pytest tests -q
```

确保全量回归。

最后运行：

```text
python examples/text_to_sql_demo.py
```

Demo应展示：

```text
Question
QueryPlan
Generated SQL
Validation Status
Trusted SQL
```

完成后标记：

# `Text-to-SQL Vertical Slice V0.1 PASSED`

---

# 三十一、紧接着下一阶段

不要立即开发Execution。

建议顺序：

## Stage 1：真实LLM接入

把：

```text
FakePlannerModel
FakeSQLModel
```

换成已有LLM基础设施的薄Adapter。

不要让Planner直接依赖某一家LLM SDK。

---

## Stage 2：Golden Dataset + Evaluation V0.1

建立真实问题集。

进行：

```text
No RAG
VS
RAG
```

比较。

这是验证Context Intelligence价值的第一场实验。

---

## Stage 3：LangGraph V0.1

把已经稳定的普通Python链：

```text
Retrieve
→ Plan
→ Generate
→ Validate
```

迁移成：

```text
State
+
Nodes
+
Edges
```

最开始保持线性。

然后逐步增加：

```text
Context Retry
Conditional Routing
Checkpoint
HITL
```

---

## Stage 4：窄版Dev Agent

再进入：

```text
自然语言开发需求
→ Dev Plan
→ DDL / ETL
→ Validation
```

---

## Stage 5：Skill / Tool

---

## Stage 6：Execution

使用本地/模拟数据库即可完成第一阶段闭环。

---

# 三十二、Stage Gate哲学

以后每个阶段都必须有三层验收。

## 1. Unit / Contract Tests

证明模块本身正确。

## 2. Integration Test

证明模块真正连接。

## 3. Demo

证明项目已经获得可见能力。

例如Text-to-SQL：

```text
Unit：
Planner / Generator

Integration：
TextToSQLService

Demo：
自然语言 → Trusted SQL
```

只有三者都存在，才宣布Stage完成。

---

# 三十三、新AI第一次接手的推荐动作

建议严格按以下顺序：

1. 阅读本文档。
2. 代码级扫描最新GitHub main。
3. 不重新设计架构。
4. 对照本文档确认：

   * TextToSQLService是否已完成；
   * Demo是否存在；
   * tests是否全绿。
5. 如果Vertical Slice已通过：

   * 直接进入真实LLM Adapter + Golden Evaluation。
6. 如果尚有失败：

   * 只修阻塞项；
   * 不增加新架构能力。
7. 整个过程中继续保持：

   * 先架构位置；
   * 再机制；
   * 再代码；
   * 再测试；
   * 再Demo。

---

# 三十四、一句话项目状态

当前 Agent3.0 已从：

> **“可信SQL审查工具”**

开始升级成：

> **“能够结合业务上下文，把自然语言问数需求转换成可信SQL的DataAgent”。**

目前最重要的任务不是继续扩宽功能，而是：

> **把 Text-to-SQL 第一条纵向产品链真正跑稳，然后使用真实LLM和Evaluation证明它有多准确，再进入LangGraph编排。**
=======

用户已表示完成上一轮闭环






【表1】

表名：dwd_hd_201_cldwdk
表用途：绿色单位贷款的明细宽表，一条数据是一笔贷款存量情况

字段：
1. 字段名：fin_org_branch_code
   类型：STRING
   含义：该笔贷款的经办金融机构统一社会信用代码
   常见业务叫法：经办机构代码

1. 字段名：fin_org_branch_area_code
   类型：STRING
   含义：该笔贷款的经办金融机构的所在地
   常见业务叫法：经办机构所在地、地区

1. 字段名：green_loan_type_code
   类型：STRING
   含义：该笔贷款属于哪一类绿色贷款
   常见业务叫法：绿色贷款类型


2. 字段名：loan_bal_rmb
   类型：DECIMAL(22,2)
   含义：该笔贷款余额
   常见业务叫法：余额

3. 字段名：rate
   类型：DECIMAL(15,5)
   含义：该笔贷款的存量利率
   常见业务叫法：利率

4. 字段名：loan_iou_no
   类型：STRING
   含义：贷款借据号
   常见业务叫法：借据号

5. 字段名：ent_code
   类型：STRING
   含义：借款人统一社会信用代码
   常见业务叫法：企业代码、借款人代码

6. 字段名：loan_grant_date
   类型：STRING
   含义：该笔贷款的发放日期
   常见业务叫法：贷款发放日期

7. 字段名：loan_due_date
   类型：STRING
   含义：该笔贷款的到期日期
   常见业务叫法：贷款到期日期

8. 字段名：fin_org_code
   类型：STRING
   含义：该笔贷款所属的金融法人机构统一社会信用代码
   常见业务叫法：金融机构代码

9. 字段名：fin_org_type_code
   类型：STRING
   含义：该笔贷款所属的金融法人机构类型
   常见业务叫法：金融机构类型
   

10. 字段名：data_date
   类型：STRING
   含义：该笔数据的报送日期
   常见业务叫法：数据日期

11. 字段名：dt
   类型：STRING
   含义：该笔数据的报送日期分区字段
   常见业务叫法：数据日期


【指标】

指标名：loan_bal_rmb
业务中文名：贷款余额、余额、存量贷款余额

计算方式：sum()

来源表：

相关字段：loan_bal_rmb

业务口径：统计某期的贷款余额，跨期不可相加

业务中还会怎么叫它：

【指标】

指标名：ent_num
业务中文名：获贷企业数、获贷企业数量、企业数量

计算方式：COUNT(DISTINCT )

来源表：

相关字段：ent_code

业务口径：去重统计获得贷款的企业数量，不可加总

业务中还会怎么叫它：

【指标】

指标名：rate
业务中文名：利率、加权利率、存量利率

计算方式：SUM(loan_bal_rmb * rate) / SUM(loan_bal_rmb)

来源表：

相关字段：rate

业务口径：计算加权利率

业务中还会怎么叫它：


1. 金额统计一般都统计当期的存量，不能跨期加总

2. 统计客户数要记得去重

3. 如果指定了贷款企业类型，需要加入对应条件



问题：
统计下本期高新技术企业的贷款余额

SQL：
SELECT SUM(loan_bal_rmb) AS loan_bal_rmb, dt
FROM odps_prd_dwd.dwd_hd_101_cldwdk
WHERE is_high_tech_ent_code = '1'
AND dt = "${p_month_yyyymm}"
GROUP BY dt

问题：
统计下本期科技中小企业的获贷企业数

SQL：
SELECT COUNT(DISTINCT ent_code) AS ent_num,dt
FROM odps_prd_dwd.dwd_hd_101_cldwdk
WHERE is_sci_medium_ent_code = '1'
AND dt = "${p_month_yyyymm}"
GROUP BY dt


问题：
按机构类型统计本期科技贷款情况

SQL：
SELECT 
    fin_org_type_code,
    SUM(loan_bal_rmb) AS loan_bal_rmb, 
    SUM(loan_bal_rmb * rate) AS SUM(loan_bal_rmb) AS rate,
    COUNT(DISTINCT ent_code) AS ent_num,
    dt
FROM odps_prd_dwd.dwd_hd_101_cldwdk
WHERE is_sci_medium_ent_code = '1'
AND dt = "${p_month_yyyymm}"
GROUP BY fin_org_type_code,dt


按地区统计科技贷款情况
分机构类型统计高新技术企业贷款情况
统计今年到期的科技贷款余额
统计本期存量科技贷款的环比、同比


以上是我整理的一张数据表的内容，我发现有个问题，就是我数仓会有很多数据表存在相似的指标字段，比如贷款余额、利率等，那么我提问的时候一定要明确是我要找哪张业务表，否则我觉得无法统计的，你看如何改进。
>>>>>>> Stashed changes

<<<<<<< Updated upstream
=======












>>>>>>> Stashed changes


**最适合的是结构化 Excel/CSV，而不是 Word/PDF；如果你能整理，我建议用一个 Excel 工作簿分 4～5 个 Sheet，这样后面可以直接用于 Context、命名规则抽取和 Warehouse Design Skill。**

## 推荐格式

### Sheet 1：`tables`
一行一张表。

| 字段 | 含义 |
|---|---|
| table_name | 物理表名 |
| table_comment | 表中文名 |
| layer | ODS/DWD/DWS/ADS 等 |
| business_domain | 业务域 |
| business_process | 业务过程 |
| grain | 表粒度，如“一笔贷款一行” |
| partition_field | 分区字段(一般含dt、sourc_bw、batch_num都为分区字段) |


### Sheet 2：`fields`
一行一个字段，**这是最重要的 Sheet**。

| 字段 | 含义 |
|---|---|
| table_name | 所属表 |
| field_name | 物理字段名 |
| field_comment | 中文含义 |
| data_type | 数据类型 |
| field_role | key/dimension/metric/attribute/partition |
| expression | 加工逻辑，可空 |
| remark | 补充说明 |

有真实表结构的话，**尽量不要只给字段名，要保留“表名 + 字段名 + 中文注释”关系**。否则像 `amt`、`type_code` 这种字段很难判断真实命名语义。

---

### Sheet 3：`naming_roots`
如果你们有词根、缩写或命名规范，单独整理。

| business_term | standard_root | type | english_name | aliases | remark |
|---|---|---|---|---|---|
| 贷款 | loan | 词根 | loan | 借款 | |
| 余额 | bal | 词根 | balance | 贷款余额 | |
| 企业 | ent | 词根 | enterprise | 公司 | |
| 机构 | org | 词根 | organization | 法人机构 | |

`type` 可以区分：

```text
word_root
abbreviation
suffix
prefix
enum
reserved_word
```

这个 Sheet 后面可以直接发展成：

```text
Naming Context
+
NamingValidator
```

---

### Sheet 4：`naming_rules`
存规范，而不是实例。

| rule_id | scope | rule | good_example | bad_example |
|---|---|---|---|---|
| R001 | table | DWS汇总表以dws_开头 | dws_green_loan_monthly | green_loan |
| R002 | field | 金额字段统一使用_amt或_bal | loan_bal | loan_money |
| R003 | field | code字段表示编码 | org_type_code | org_type |

如果规范目前只有文档，没有结构化数据，**直接把原始规范文档一起给我也可以**，不需要你为了我人工全部重录。

---

### Sheet 5：`approved_examples`（很推荐）
放你们认为“命名得比较标准”的真实表和字段。

| object_type | physical_name | business_meaning | why_good |
|---|---|---|---|
| table | dwd_hd_201_cldwdk | 绿色单位贷款明细宽表 | 已上线标准表 |
| field | loan_bal_rmb | 人民币贷款余额 | 已有统一口径 |

这个 Sheet 很有价值，因为：

> **规范告诉 Agent“应该怎样”，真实优秀案例告诉 Agent“你们实际上怎样落地”。**

两者不能完全互相替代。

---

# 如果数据量很大

几十万字段也没问题，优先给：

```text
.xlsx
或
tables.csv
fields.csv
naming_roots.csv
naming_rules.csv
```

如果超过 Excel 方便处理的规模，可以直接给多个 CSV 压缩包。

**不要为了整理得非常漂亮而人工加工太多。** 如果你手里本来就是元数据导出，类似：

```text
database
table_name
table_comment
column_name
column_comment
data_type
```

先原样给我也行，我可以先分析现有命名模式，再告诉你还缺什么。

---

## 我最希望你至少提供的 5 列

如果时间有限，最低要求就是：

```text
table_name
table_comment
field_name
field_comment
data_type
```

只要这五列规模足够大，我就可以先分析：

- 表命名结构；
- 字段常用词根；
- 缩写习惯；
- `code/name/id/amt/bal/num/cnt/rate` 等后缀规律；
- 同义词是否存在多种命名；
- 哪些命名已经形成事实标准；
- 哪些命名存在不一致；
- 后续怎样转成 Agent 可消费的 Naming Context。




1. 我已经将最新代码git上去了 你的上下文已经很长了，接下来我希望你能做一次完整的工作交接。 请根据我们之前的全部对话内容，自动梳理并写一份结构清晰的《工作交接文档》。这份文档的受众是“下一个新开启对话的 AI”，目标是让它通过读取该文档，并结合 GitHub 上的项目内容，能够无缝接替你的工作继续完成。你工作的交接文档更多应该给出技术架构、历史开发过程、未来发展方向，不用太多局限于细节和无意义的地方，让后续的对话窗口通过阅读github代码继续开展工作，请你梳理并涵盖以下核心维度（具体结构与呈现方式由你自由组织）： 
   - 工作职责与工作要求（包括我给你的角色定位、规范标准，以及曾经纠正过的避坑事项） 
   - 任务内容与工作方式（包括我们日常的协作模式、处理问题的思路或特定偏好） 
   - 目前商定的项目架构和后续工作方针
   - 项目进度（已完成的成果、当前状态以及紧接着需要完成的下阶段任务） 
   - GitHub 项目对接说明（结合仓库代码的注意事项与核心关注点） 
   - 其余你觉得需要加入的内容 非常感谢你这段时间对我的帮助，还有什么需要对我说的吗


