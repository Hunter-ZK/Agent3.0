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

4. TypeError: TrustedSQLWorkflow.__init__() got an unexpected keyword argument 'explain_agent'

class TrustedSQLWorkflow:

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
    

    def run(self, sql: str, file_path: str = "<memory>") -> TrustedSQLWorkflowResult:
        trace_id = str(uuid4())
        route_history: list[str] = []

        explain_response = self.engine.explain(
            SQLExplainRequest(sql=sql, file_path=file_path, trace_id=trace_id)
        )

        route_history.append("explain")

        if not explain_response.success:
            return TrustedSQLWorkflowResult(
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
            return TrustedSQLWorkflow(
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
            return TrustedSQLWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="review_failed",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
                error_message=review_response.error_message,
            )
        
        if review_response.issue_count == 0:
            return TrustedSQLWorkflowResult(
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
            return TrustedSQLWorkflowResult(
                success=False,
                trace_id=trace_id,
                final_status="context_required",
                explain_response=explain_response,
                review_response=review_response,
                route_history=route_history,
            )

        if need_human_confirm or can_auto_fix is not True:
            return TrustedSQLWorkflowResult(
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
                return TrustedSQLWorkflowResult(
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
                return TrustedSQLWorkflowResult(
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
我现在其实不太能理解我的trusted_sql_workflow里的流程了，为什么有的参数是agent、有的是egine,之前还有service，互相都是什么关系。


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
TrustedSQLWorkflow
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
TrustedSQLWorkflow
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
TrustedSQLWorkflow
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


1. 我觉得llm-fix后应该进入的就是review阶段，也是llm吧，你解释一下是不是
2. rules/basic这个文件我觉得有点不合适，跟我之前的理念一样，就是难道我需要去列举各种情况来复核代码吗，还是可以调用llm去完成呢？
3. llm文件里单独的prompts文件命名呢？请你确认下文件内容和命名
4. 为什么又有sql_review_service和review_service,请你检查



======================================================================
DETERMINISTIC ONLY
======================================================================
success: True
status: no_issue
error: None
route: ['explain_skipped', 'review']
trusted_sql:
SELECT SUM(loan_bal_rmb) AS tech_loan_balance
FROM odps_prd_dwd.ods_hd_100_cldkxx
WHERE is_high_tech_mfg_loan_code = '1'
  AND dt = '202607'


issues:

======================================================================
REAL LLM REVIEW
======================================================================
success: True
status: trusted_with_advisories
error: None
route: ['explain', 'review']
trusted_sql:
SELECT SUM(loan_bal_rmb) AS tech_loan_balance
FROM odps_prd_dwd.ods_hd_100_cldkxx
WHERE is_high_tech_mfg_loan_code = '1'
  AND dt = '202607'


issues:
{'rule_id': 'LLM_EXAMPLE', 'title': 'dt字段过滤条件可能无效', 'severity': 'medium', 'message': '表 ods_hd_100_cldkxx 在元数据中标记为非分区表，但 SQL 中使用了 dt 字段进行过滤。若 dt 是普通字段，则过滤条件可能有效；若 dt 是分区字段但元数据未正确识别，则可能导致查询全表扫描。需要确认 dt 字段的实际用途。', 'suggestion': "确认 dt 字段是否为分区字段，以及 '202607' 是否为有效的日期或月份值。若 dt 是普通字段，建议检查数 据中 dt 的格式和取值范围。", 'evidence': "SQL 中使用了 dt = '202607'，但元数据未显示分区信息", 'category': 'filter_condition', 'source': 'llm', 'confidence': 0.8, 'location': None, 'action': 'advisory', 'auto_fixable': False, 'requires_metadata': False, 'requires_knowledge': False, 'metadata': {}, 'blocking': False}
{'rule_id': 'LLM_EXAMPLE', 'title': 'is_high_tech_mfg_loan_code 字段含义不明确', 'severity': 'medium', 'message': "is_high_tech_mfg_loan_code 字段的取值含义未在元数据中说明，假设 '1' 表示是，但需确认该代码的实际业务含义，避免过滤条件错误。", 'suggestion': "确认 is_high_tech_mfg_loan_code 的取值字典，确保 '1' 代表高技术制造业贷款。", 'evidence': "SQL 中使用了 is_high_tech_mfg_loan_code = '1'，但元数据未提供取值说明", 'category': 'business_semantics', 'source': 'llm', 'confidence': 0.7, 'location': None, 'action': 'advisory', 'auto_fixable': False, 'requires_metadata': False, 'requires_knowledge': False, 'metadata': {}, 'blocking': False}
{'rule_id': 'LLM_EXAMPLE', 'title': '潜在性能问题：全表扫描风险', 'severity': 'low', 'message': '如果表数据量较大，且 dt 字段未建立索引或不是分区字段，全表扫描可能导致性能问题。', 'suggestion': '考虑在 dt 字段上建立索引，或确认表的分区策略。', 'evidence': '表为非分区表，且 dt  字段过滤条件可能未利用索引', 'category': 'performance', 'source': 'llm', 'confidence': 0.6, 'location': None, 'action': 'advisory', 'auto_fixable': False, 'requires_metadata': False, 'requires_knowledge': False, 'metadata': {}, 'blocking': False}


success: False
status: review_failed
error: LLM rule_id 必须以 LLM_ 开头。
route: ['explain', 'review']
trusted_sql: None

[Review]
success: False
error: LLM rule_id 必须以 LLM_ 开头。
issues:

2. planer prompt，未指定本期，我觉得可以用时间参数替代，没有任何问题！

3. 



==============================================================================
Agent3.0 · Text-to-SQL Real LLM Evaluation V2
==============================================================================

==============================================================================
Agent3.0 · Text-to-SQL Real LLM Evaluation V2
==============================================================================

[1/2] high_tech_yoy
question: 统计高新技术企业贷款余额同比
result: PASS
initial: result
validation: trusted_with_advisories
semantic: pass
reason: Trusted SQL 路径通过。

[1/2] high_tech_yoy
question: 统计高新技术企业贷款余额同比
result: FAIL
initial: result
validation: review_failed
semantic: None
reason: Text-to-SQL 最终 success=False; validation=review_failed; semantic=None
validation_error: 只有 action=auto_fix 时 auto_fixable 才能为 true。

[2/2] explicit_green_current
question: 统计本期绿色贷款余额
result: FAIL
initial: result
validation: review_failed
semantic: None
reason: Text-to-SQL 最终 success=False; validation=review_failed; semantic=None
validation_error: LLM 不允许直接生成 BLOCK / IGNORE action。

第一条结果我发现有时候会通过，这是为什么



1. 请你重新查看llm/reviewer.py，目前逻辑很混乱
2. [2/2] explicit_green_current
question: 统计本期绿色贷款余额
result: FAIL
initial: result
validation: blocked
semantic: None
reason: Text-to-SQL 最终 success=False; validation=blocked; semantic=None
validation_error: A blocking issue exists.



python -m sql_pilot_engine.metadata.ingestion.rebuild.rebuild_metadata_database --metadata-source ./data/metadata/raw/全量字段.xlsx --target-db ./data/metadata/agent_metadata.db




##############################################################################
explicit_high_tech_month
统计2026年7月高新技术企业的贷款余额
##############################################################################
LLM review first parse failed. error=LLM issue 缺少字段：['action', 'confidence', 'evidence', 'message', 'rule_id', 'title'] raw_result={'action': 'advisory', 'issues': [{'severity': 'medium', 'category': 'date_and_partition', 'description': "dt 字段值为 '202607'，格式为 YYYYMM，疑似为月份分区。若该表为日分区表，则此过滤条件可能无法命中任何分区或导致全表扫描。请确认 dt 的分区粒度。", 'suggestion': "确认 dt 的分区粒度。若为日分区，应使用 'YYYYMMDD' 格式或使用日期函数（如 MAX(dt)）获取最新分区。"}, {'severity': 'low', 'category': 'null_handling', 'description': 'SUM(loan_bal_rmb) 会忽略 NULL 值，但若 loan_bal_rmb 存在 NULL 且业务上应视为 0，则结果可能偏低。', 'suggestion': '若业务上 NULL 应视为 0，请使用 COALESCE(loan_bal_rmb, 0) 或确认数据质量。'}], 'summary': 'SQL 逻辑简单，但需确认分区粒度与 NULL 处理。'}
LLM review repair parse failed. first_error=LLM issue 缺少字段：['action', 'confidence', 'evidence', 'message', 'rule_id', 'title'] second_error=LLM issue 缺少字段：['suggestion'] raw_result={'action': 'advisory', 'issues': [{'severity': 'medium', 'category': 'date_and_partition', 'description': "dt 字段值为 '202607'，格式为 YYYYMM，疑似为月份分区。若该表为日分区表，则此过滤条件可能无法命中任何分区或导致全表扫描。请确认 dt 的分区粒度。", 'suggestion': "确认 dt 的分区粒度。若为日分区，应 使用 'YYYYMMDD' 格式或使用日期函数（如 MAX(dt)）获取最新分区。"}, {'severity': 'low', 'category': 'null_handling', 'description': 'SUM(loan_bal_rmb) 会忽略 NULL 值，但若 loan_bal_rmb 存在 NULL 且业务上应视为 0，则结果可能偏低。', 'suggestion': ' 若业务上 NULL 应视为 0，请使用 COALESCE(loan_bal_rmb, 0) 或确认数据质量。'}], 'summary': 'SQL 逻辑简单，但需确认分区粒度与 NULL 处理。'} repaired_result={'action': 'advisory', 'issues': [{'rule_id': 'DATE_PARTITION_FORMAT_MISMATCH', 'title': 'dt 字段疑似月份分区，但格式为 YYYYMM', 'message': "dt 字段值为 '202607'，格式为 YYYYMM，疑似为月份分区。若该表为日分区表，则此过滤条件可能无法命中任何分区或导致全表扫描。请确认 dt 的分区粒度。", 'evidence': "dt = '202607'", 'confidence': 'medium', 'action': 'advisory', 'severity': 'medium', 'category': 'date_and_partition'}, {'rule_id': 'NULL_HANDLING_IN_SUM', 'title': 'SUM 函数忽略 NULL 值', 'message': 'SUM(loan_bal_rmb) 会忽略 NULL 值，但若 loan_bal_rmb 存在 NULL 且业务上应视为 0，则结果 可能偏低。', 'evidence': 'SUM(loan_bal_rmb)', 'confidence': 'low', 'action': 'advisory', 'severity': 'low', 'category': 'null_handling'}], 'summary': 'SQL 逻辑简单，但需确认分区粒度与 NULL 处理。'}

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: True
validation: review_failed
semantic_status: None
reason: SQL Trust failed: review_failed; Semantic failed: None; issues=(); system error: LLM issue 缺少字段：['suggestion']
validation_error: LLM issue 缺少字段：['suggestion']

==============================================================================
Evaluation Summary
==============================================================================
runs: 1
planning_accuracy: 1/1 (100.0%)
clarification_accuracy: 1/1 (100.0%)
sql_trust_rate: 0/1 (0.0%)
semantic_pass_rate: 0/1 (0.0%)
final_success_rate: 0/1 (0.0%)
system_error_rate: 1/1 (100.0%)
stable_cases: 0/1

Per-case stability
- explicit_high_tech_month: 0/1


Traceback (most recent call last):
  File "<stdin>", line 40, in <module>
RuntimeError: Unexpected clarification: 您的问题不明确，请具体说明需要统计的内容（例如：科技贷款余额、绿色贷款获贷企业数等 ）以及统计维度（如按地区、机构类型等）。

PS D:\学习\DataAgent\sqlpilot_phase_b1_engine\sqlpilot-latest-source> python examples/text_to_sql_demo.py `
>>   --use-real-llm `
>>   --question "统计本期绿色贷款加权利率" `
>>   --dialect maxcompute `
>>   --log-level INFO
2026-08-24 02:52:31,752 INFO sql_pilot_engine.generation.deepseek_model run=- llm.request provider=deepseek model=deepseek-chat prompt_chars=8038
2026-08-24 02:52:33,660 INFO httpx run=- HTTP Request: POST https://api.deepseek.com/chat/completions "HTTP/1.1 200 OK"
2026-08-24 02:52:34,706 INFO sql_pilot_engine.generation.deepseek_model run=- llm.response provider=deepseek model=deepseek-chat response_chars=308 elapsed_ms=2954
Traceback (most recent call last):
  File "D:\学习\DataAgent\sqlpilot_phase_b1_engine\sqlpilot-latest-source\examples\text_to_sql_demo.py", line 452, in <module>
    main()
    ~~~~^^
  File "D:\学习\DataAgent\sqlpilot_phase_b1_engine\sqlpilot-latest-source\examples\text_to_sql_demo.py", line 314, in main 
    response = service.generate(
        TextToSQLRequest(
    ...<2 lines>...
        )
    )
  File "D:\学习\DataAgent\sqlpilot_phase_b1_engine\sqlpilot-latest-source\sql_pilot_engine\capabilities\text_to_sql.py", line 62, in generate
    state = self._graph.start(
        thread_id=thread_id,
    ...<7 lines>...
        ),
    )
  File "D:\学习\DataAgent\sqlpilot_phase_b1_engine\sqlpilot-latest-source\sql_pilot_engine\runtime\query_graph.py", line 997, in start
    return self.graph.invoke(
           ~~~~~~~~~~~~~~~~~^
        initial_state,
        ^^^^^^^^^^^^^^
        config=config,
        ^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\langgraph\pregel\main.py", line 3913, in invoke
    for chunk in self.stream(
                 ~~~~~~~~~~~^
        input,
        ^^^^^^
    ...<11 lines>...
        **kwargs,
        ^^^^^^^^^
    ):
    ^
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\langgraph\pregel\main.py", line 2967, in stream
    for _ in runner.tick(
             ~~~~~~~~~~~^
        [t for t in loop.tasks.values() if not t.writes],
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<2 lines>...
        schedule_task=loop.accept_push,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ):
    ^
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\langgraph\pregel\_runner.py", line 207, in tick
    run_with_retry(
    ~~~~~~~~~~~~~~^
        t,
        ^^
    ...<10 lines>...
        },
        ^^
    )
    ^
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\langgraph\pregel\_retry.py", line 617, in
 run_with_retry
    return task.proc.invoke(task.input, config)
           ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\langgraph\_internal\_runnable.py", line 707, in invoke
    input = context.run(step.invoke, input, config, **kwargs)
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\langgraph\_internal\_runnable.py", line 447, in invoke
    ret = self.func(*args, **kwargs)
  File "D:\学习\DataAgent\sqlpilot_phase_b1_engine\sqlpilot-latest-source\sql_pilot_engine\runtime\query_graph.py", line 351, in _plan_query
    outcome = self.planner.plan(
        query_context=(
            query_context
        ),
    )
  File "D:\学习\DataAgent\sqlpilot_phase_b1_engine\sqlpilot-latest-source\sql_pilot_engine\generation\planner.py", line 63, in plan
    data = json.loads(raw)
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\json\__init__.py", line 352, in loads
    return _default_decoder.decode(s)
           ~~~~~~~~~~~~~~~~~~~~~~~^^^
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\json\decoder.py", line 345, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Lenovo\AppData\Local\Python\pythoncore-3.14-64\Lib\json\decoder.py", line 363, in raw_decode
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)





2026-08-24 02:59:27,799 DEBUG sql_pilot_engine.generation.planner run=- planner.response
```json
{
  "status": "ready",
  "plan": {
    "tables": ["ods_hd_200_cldkxx"],
    "dimensions": [],
    "metrics": ["green_loan_weighted_rate"],
    "filters": ["dt = '${p_month_yyyymm}'"],
    "group_by": [],
    "requirements": ["按贷款余额加权计算绿色贷款存量利率：SUM(loan_bal_rmb * rate) / SUM(loan_bal_rmb)"]
  }
}
```




======================================================================
DETERMINISTIC ONLY
======================================================================
success: True
status: no_issue
error: None
route: ['explain_skipped', 'review']
trusted_sql:
SELECT SUM(loan_bal_rmb) AS tech_loan_balance
FROM odps_prd_dwd.ods_hd_100_cldkxx
WHERE is_high_tech_mfg_loan_code = '1'
  AND dt = '202607'


ISSUES:

======================================================================
REAL LLM REVIEW
======================================================================
success: False
status: context_required
error: Additional context is required.
route: ['explain', 'review']
trusted_sql: None

ISSUES:
{'rule_id': 'LLM_AGG_GRANULARITY', 'title': '聚合粒度与指标口径需确认', 'severity': 'medium', 'message': 'SQL 对 loan_bal_rmb 求和，但未明确该表的数据粒度（如每笔贷款、每笔借据、每笔合同等）。若表为明细级，SUM 结果即为科技贷款余额；若表已按机构或日期聚合，则 SUM 可能造成重复计算或口径偏差。', 'suggestion': '确认 ods_hd_100_cldkxx 表的数据粒度，并明确指标口径（如贷款 余额应为时点值，避免对多笔记录重复求和）。若表为明细，建议增加去重或明确唯一键。', 'evidence': "SELECT SUM(loan_bal_rmb) AS tech_loan_balance FROM odps_prd_dwd.ods_hd_100_cldkxx WHERE is_high_tech_mfg_loan_code = '1' AND dt = '202607'", 'category': 'aggregation', 'source': 'llm', 'confidence': 0.7, 'location': None, 'action': 'context_required', 'auto_fixable': False, 'requires_metadata': False, 'requires_knowledge': False, 'metadata': {}, 'blocking': True}
{'rule_id': 'LLM_FILTER_CODE_VALUE', 'title': "过滤条件 is_high_tech_mfg_loan_code = '1' 的语义需确认", 'severity': 'medium', 'message': "字段 is_high_tech_mfg_loan_code 为代码字段，但元数据未提供代码值含义。'1' 是否表示“是”或“高技术制造业贷款”需确认，否则可能过滤错误。", 'suggestion': "确认 is_high_tech_mfg_loan_code 的代码字典，确保 '1' 表示“是”或“高技术制造业贷款”。若代码含义不同，需调整过滤条件。", 'evidence': "WHERE is_high_tech_mfg_loan_code = '1'", 'category': 'filter', 'source': 'llm', 'confidence': 0.6, 'location': None, 'action': 'context_required', 'auto_fixable': False, 'requires_metadata': False, 'requires_knowledge': False, 'metadata': {}, 'blocking': True}
{'rule_id': 'LLM_PARTITION_DATE', 'title': "分区字段 dt 使用月份值 '202607'，需确认分区粒度", 'severity': 'low', 'message': "dt 字段被用作分区，但元数据未明确分区粒度。'202607' 看起来是月份分区（2026年7月），但若实际为日分区，则可能无法命中任何分区或导致扫描范围错误。", 'suggestion': "确认 dt 的分区粒度（日、月等）。若为日分区，应使用具体日期（如 '20260701'）或使用日期函数（如 dt >= '20260701' AND dt <= '20260731'）。", 'evidence': "AND dt = '202607'", 'category': 'partition', 'source': 'llm', 'confidence': 0.5, 'location': None, 'action': 'context_required', 'auto_fixable': False, 'requires_metadata': False, 'requires_knowledge': False, 'metadata': {}, 'blocking': True}
{'rule_id': 'LLM_PERF_SCAN_RANGE', 'title': '全表扫描风险：未使用分区裁剪', 'severity': 'low', 'message': "虽然 WHERE 条件 包含 dt = '202607'，但元数据表明该表未分区（Is Partitioned: False）。因此该查询可能扫描全表，若表数据量较大，性能风险较高。", 'suggestion': '确认表是否实际分区。若未分区，建议考虑按数据日期字段（如 data_date）进行过滤，或优化表结构为分区表。若已 分区，确保 dt 为分区字段。', 'evidence': "Metadata: Is Partitioned: False; SQL: WHERE dt = '202607'", 'category': 'performance', 'source': 'llm', 'confidence': 0.8, 'location': None, 'action': 'advisory', 'auto_fixable': False, 'requires_metadata': False, 'requires_knowledge': False, 'metadata': {}, 'blocking': False}


==============================================================================
Agent3.0 · Text-to-SQL Evaluation V2
==============================================================================
cases: 11
repeat: 1

##############################################################################
explicit_high_tech_month
统计2026年7月高新技术企业的贷款余额
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
current_high_tech
统计本期高新技术企业的贷款余额
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
high_tech_yoy
统计高新技术企业贷款余额同比
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
high_tech_mom
统计高新技术企业贷款余额环比
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
tech_enterprise_count
统计本期科技贷款获贷企业数
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
tech_weighted_rate
统计本期科技贷款加权利率
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
tech_balance_by_region
统计本期各地区科技贷款余额
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: blocked
semantic_status: None
reason: SQL Trust failed: blocked; Semantic failed: None; issues=()
validation_error: A blocking issue exists.

##############################################################################
tech_balance_by_org_type
统计本期各金融机构类型科技贷款余额
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
ambiguous_balance
统计贷款余额
##############################################################################
Deserializing unregistered type sql_pilot_engine.context.models.ContextDocumentKind from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('sql_pilot_engine.context.models', 'ContextDocumentKind')]
Deserializing unregistered type sql_pilot_engine.context.models.ContextDocument from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('sql_pilot_engine.context.models', 'ContextDocument')]
Deserializing unregistered type sql_pilot_engine.context.models.RetrievedDocument from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('sql_pilot_engine.context.models', 'RetrievedDocument')]
Deserializing unregistered type sql_pilot_engine.context.builder.QueryContext from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('sql_pilot_engine.context.builder', 'QueryContext')]

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
ambiguous_rate
统计本期贷款利率
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

##############################################################################
tech_rate_by_org_type
统计本期各金融机构类型科技贷款加权利率
##############################################################################

run=1 final=FAIL
planning: True
clarification: True
sql_trust: False
semantic: False
system_error: False
validation: context_required
semantic_status: None
reason: SQL Trust failed: context_required; Semantic failed: None; issues=()
validation_error: Additional context is required.

==============================================================================
Evaluation Summary
==============================================================================
runs: 11
planning_accuracy: 11/11 (100.0%)
clarification_accuracy: 11/11 (100.0%)
sql_trust_rate: 0/11 (0.0%)
semantic_pass_rate: 0/11 (0.0%)
final_success_rate: 0/11 (0.0%)
system_error_rate: 0/11 (0.0%)
stable_cases: 0/11

Per-case stability
- explicit_high_tech_month: 0/1
- current_high_tech: 0/1
- high_tech_yoy: 0/1
- high_tech_mom: 0/1
- tech_enterprise_count: 0/1
- tech_weighted_rate: 0/1
- tech_balance_by_region: 0/1
- tech_balance_by_org_type: 0/1
- ambiguous_balance: 0/1
- ambiguous_rate: 0/1
- tech_rate_by_org_type: 0/1








python examples/text_to_sql_demo.py --question "统计本期高新技术企业贷款余额" --use-real-llm --log-level DEBUG







你的上下文已经很长了，接下来我希望你能做一次完整的工作交接。 请根据我们之前的全部对话内容，自动梳理并写一份结构清晰的《工作交接文档》。这份文档的受众是“下一个新开启对话的 AI”，目标是让它通过读取该文档，并结合 GitHub 上的项目内容，能够无缝接替你的工作继续完成。 请你梳理并涵盖以下核心维度（具体结构与呈现方式由你自由组织）： 

\- **\*\*工作职责与工作要求\*\***（包括我给你的角色定位、规范标准，以及曾经纠正过的避坑事项） 

\- **\*\*任务内容与工作方式\*\***（包括我们日常的协作模式、处理问题的思路或特定偏好） 

\- 工作的目标以及目前确定下来的技术架构和未来的项目发展内容

\- **\*\*项目进度\*\***（已完成的成果、当前状态以及紧接着需要完成的下阶段任务） 

\- **\*\*GitHub 项目对接说明\*\***（结合仓库代码的注意事项与核心关注点） 

\- 在这段对话过程中我的一些重要要求和你的自我反思总结 





# Agent3.0 / DataAgent 工作交接文档

**交接日期：2026-08-24**
**目标读者：下一次新开启对话中的主开发 AI**
**GitHub：`Hunter-ZK/Agent3.0`，默认分支 `main`**

> 本文档用于让下一位 AI 直接接续 Agent3.0 / DataAgent 的开发、架构收口、调试和技术训练工作。
> 当前 GitHub 最新确认提交为 **`20260824-8`，SHA `d1f79c5a045b17cb4ea5f4c4f3a4cfc23b42b11e`**。该提交已经补上 ReviewService 的 QueryContext 传递、Reviewer 原始返回 DEBUG 日志、Context 回归测试，并清理了 `auto_fixable` Prompt 冲突。

---

# 一、项目定位与最终目标

Agent3.0 / DataAgent 不是一个“让 AI 一次性生成代码”的项目，而是一个长期、真实的软件研发与技术训练项目。

项目同时有两个目标：

1. **做出真正可运行、可测试、可维护、可持续扩展的 DataAgent。**
2. **让用户最终能够独立理解、设计、修改和维护这个系统，而不是机械复制 AI 给出的代码。**

因此下一位主开发 AI 既是：

* 技术架构师；
* 主开发指导者；
* 代码 Review / Debug 负责人；
* DataAgent 产品与技术顾问；
* Stage Gate / Evaluation 设计者。

但不是持续出题的学习教练。主开发窗口应以：

> **高密度推进真实项目 + 把关键技术讲透**

为主。

---

# 二、用户的工作要求与协作规范

这一部分必须长期遵守。

## 2.1 不允许擅自改变需求或架构

用户已经明确要求：

* 不擅自改需求；
* 不未经授权扩展范围；
* 不把建议说成已经完成；
* 不把推测说成事实；
* 不重复已经完成的工作；
* 不为了“架构漂亮”不停增加新 DTO、新层、新接口。

特别是以下变化必须**先讨论方案，再开发**：

* 大规模架构调整；
* 新增共享模块；
* 持久化方案变化；
* 主 Workflow 改造；
* 公共 DTO / State 大改；
* Capability 边界调整；
* Context ownership 改变。

正确工作方式：

```text
发现问题
↓
说明真实问题
↓
提出 2~3 个方案（必要时）
↓
说明 Trade-off
↓
用户确认
↓
进入代码修改
```

禁止：

```text
先写一堆代码
↓
发现设计不对
↓
再重新定义架构
```

---

## 2.2 Debug 必须“验证后修改”，禁止根据猜测直接给方案


用户明确指出：

> **推测问题以后应该去验证，而不是直接给解决方案。**

后续排查必须遵循：

```text
Observe
↓
Hypothesis
↓
Verify actual call chain / raw I/O / minimal reproduction
↓
Exclude alternatives
↓
【已确认根因】 / 【仍是推测】
↓
Production Fix
```

尤其涉及：

* Context 为什么丢；
* Review 为什么 `context_required`；
* Metadata 为什么 NOT_FOUND；
* SQL 为什么被 BLOCK；
* LLM 输出为什么异常；

必须先获取实际证据。

不能再：

> “我觉得应该是 X，所以你改 Y。”

---

## 2.3 代码交付方式

### 小改动

优先：

```text
具体文件
+ 精确位置
+ 原代码
+ 修改后代码
+ 为什么
+ 怎么验证
```

不要动不动整文件替换。

### 大改 / Test / Demo / Fixture

可以提供完整可复制代码。

用户特别要求：

> 标注【可直接复制】的代码，尤其测试文件，应尽量完整，不给只有几行的残片。

---

## 2.4 开发教学节奏

用户不是传统软件工程师，但具有较强：

* SQL；
* 数仓；
* MaxCompute；
* DataWorks；
* 数据建模；
* 产品；
* 项目管理；

背景。

讲解软件架构时，要解释：

```text
为什么有这一层
解决什么问题
输入是什么
输出是什么
谁调用谁
如果没有这一层会怎样
```

尤其：

* DTO；
* Protocol；
* Service；
* Engine；
* Workflow；
* Factory；
* Dependency Injection；
* State；
* Context；

不要只给定义。

同时用户不喜欢开发节奏过碎：

> **一个阶段只引入一个主要架构概念，但一个阶段内部要高密度做完整。**

---

# 三、GitHub 工作规范

仓库：

```text
https://github.com/Hunter-ZK/Agent3.0
```

Python：

```text
>=3.14,<3.15
```

默认分支：

```text
main
```

## 3.1 什么时候扫描 GitHub

用户已经明确：

**默认不要每轮扫描 GitHub。**

只有用户明确说：

* 已 push；
* 查看最新代码；
* 检查 GitHub；
* 全仓扫描；
* 项目监督；
* 做工作交接；
* 根据最新代码重新判断；

时，再扫描。

当前这份交接已经进行了一次最新校准。

最新远端提交为：

```text
20260824-8
d1f79c5a045b17cb4ea5f4c4f3a4cfc23b42b11e
```

新窗口首次接手时，可以再确认一次 HEAD；完成首次校准后，不要每轮重复扫。

---

## 3.2 GitHub 扫描不能只看 README

应至少关注：

```text
latest commits
src/core code
runtime/workflow
services
LLM executors/prompts
metadata
tests
examples
pyproject.toml
真正调用链
```

代码事实优先级：

```text
用户本地实际运行输出
>
GitHub 当前 main
>
历史交接文档
>
AI 对历史的记忆
```

如果用户本地已经修改但未 push，本地运行结果优先。

---

# 四、V1 产品目标

当前 V1 只保留四个核心成果：

1. **Trusted SQL**
2. **Text-to-SQL 智能问数**
3. **窄版数仓开发**
4. **Agent / Skill / Evaluation 基础能力**

总体产品主链：

```text
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
SQL Validation / Trusted SQL
 ↓
Execution（后置）
 ↓
Result
```

横向：

```text
Evaluation
Tool Registry
Skill Registry
Observability
LLM Adapter
```

## 非常重要

Text-to-SQL V1 最终产物：

> **准确、可信的 SQL**

不是：

> SQL 必须实际执行并返回数据库结果。

当前不把：

* DuckDB；
* 真实数据库连接；
* Production Execution；

作为 Text-to-SQL Stage Gate。

---

# 五、当前冻结的软件分层

建议长期保持：

```text
app
→ Composition Root / Factory

capabilities
→ 产品能力 Facade

runtime / workflow
→ 状态、路由、Retry、HITL、多阶段流程

engine
→ Shared SQL Core 稳定门面

services
→ Review / Fix / Explain / Optimize 等内部用例

llm
→ Reviewer / Fixer / Explainer / Optimizer / Prompt / Client

analysis
metadata
validation
rules
fixing
→ 确定性基础能力

core
→ 稳定领域模型

schemas
→ 外部 Request / Response / Capability DTO
```

原则：

> 每一层必须有不可替代职责。

不要为了“抽象统一”建立无意义：

```text
BaseService
UniversalAgent
UniversalContext
UniversalCapabilityContract
```

---

# 六、Trusted SQL 架构

当前 Trusted SQL 是整个项目最成熟的 Shared Capability。

核心流程：

```text
SQL
 ↓
SQLAnalysisAdapter / SQLGlot
 ↓
SQLFacts
 ↓
Deterministic Guardrails
 ├─ Syntax
 ├─ Dangerous Operations
 └─ Metadata Physical Truth
 ↓
LLM Reviewer
 ↓
ReviewResult
 ↓
Routing
 ├─ advisory only → Trusted
 ├─ context_required → stop
 ├─ human_review → stop
 ├─ block → stop
 └─ auto_fix
       ↓
      Fix
       ↓
      Full Re-review
       ↓
      Critic
       ↓
      Trusted SQL
```

---

## 6.1 SQL 分析 ADR

已经冻结：

```text
SQLGlot
↓
Thin SQLAnalysisAdapter
↓
Agent3.0 SQLFacts / DTO
```

不要恢复：

* 自研 parser；
* 自研 Scope；
* 自研 Lineage；
* 每条 Rule 自己 Parse SQL。

原则：

> Parse once per review/stage。

---

## 6.2 Issue / Routing Contract

`Issue.action` 是唯一可信生命周期行为事实源。

主要 Action：

```text
ADVISORY
AUTO_FIX
CONTEXT_REQUIRED
HUMAN_REVIEW
BLOCK
IGNORE
```

规则：

* LLM 不允许产生 `BLOCK`；
* `BLOCK` 只属于 deterministic evidence；
* LLM 输出 block 时内部降权为 human_review；
* Severity 只是风险等级，不决定 Trusted SQL；
* `blocking` 是从 action 派生的兼容属性；
* advisory-only SQL 可以成为 Trusted SQL；
* Fix 后必须完整 Re-review；
* Re-review 后 Critic 才能放行。

---

# 七、Context Intelligence：本轮最终确认的架构

这是本次交接最重要的架构决策。

## 7.1 一个 Turn 只有一个 QueryContext

用户最终明确要求：

> **同一个问题只有一个 Context，传给所有需要它的接口即可。**

当前定义：

```text
QueryContext
=
当前 User Question / Turn 的唯一 Task Context
```

包含：

```text
question

semantic_context
→ Semantic Knowledge

business_knowledge
→ RAG Business Knowledge
→ Mandatory / Fixed Business Rules

verified_sql
→ Verified SQL Knowledge

session_context
→ 当前任务用户补充/澄清的信息
```

---

## 7.2 Context 构建一次，不因消费者变化

正确架构：

```text
Context Intelligence
       ↓
   QueryContext
       │
       ├─ Planner
       ├─ Generator
       ├─ Validation
       ├─ Reviewer
       ├─ Fixer
       └─ Semantic Validator
```

**必须是同一个对象。**

禁止：

```text
PlannerContext
GenerationContext
ReviewTaskContext
FixContext
ValidationContext
Context Projection
Context Inheritance
重新 RAG
重新构建 Semantic Context
```

---

## 7.3 QueryAgentState 是 QueryContext 的 Runtime 持有者

当前代码已经：

```text
QueryAgentState
└─ query_context
```

Context Builder 创建后进入 State。

因此 Text-to-SQL Graph 内部：

```text
state["query_context"]
→ Planner
→ Generator
→ Validate
→ Semantic Validator
```

不要重新增加另一份 semantic_context 到 State。

---

## 7.4 为什么 TrustedSQLWorkflow 可以接 QueryContext

这是本轮讨论后最终确认：

```text
QueryAgentState
属于 Text-to-SQL Runtime

TrustedSQLWorkflow
属于独立 Trusted SQL 子工作流
```

所以不能：

```text
TrustedSQLWorkflow
直接依赖 QueryAgentState
```

否则 SQL Core 会反向依赖 Text-to-SQL / LangGraph。

正确：

```python
trusted_sql_workflow.run(
    generated_sql,
    query_context=state["query_context"],
)
```

即：

> **在 Workflow 边界把同一个 QueryContext 传进去一次。**

---

## 7.5 SQLExecutionContext 不是第二套业务 Context

当前存在：

```text
SQLExecutionContext
```

其含义是：

> SQL Core 一次运行所需的执行参数容器。

例如：

```text
sql
dialect
metadata_provider
llm config
trace_id
retry
query_context → 引用唯一 QueryContext
```

因此：

```text
QueryContext
= 这个任务“已经知道什么”

SQLExecutionContext
= 当前 SQL Core “怎么执行”
```

不能把二者混为一谈。

---

# 八、Planning / Generation / Explain / Validation 的职责区别

下一位 AI 应保持这个理解。

## Planning

回答：

> 用户到底要查询什么？

输出：

```text
table
metric
dimension
filter
group_by
requirements
```

属于原子 Stage。

---

## Generation

回答：

> 根据 QueryPlan + QueryContext，SQL 怎么写？

属于单次 Generator。

Retry 是否再次调用 Generator，由外层 Graph 决定。

---

## Explain

回答：

> 已经存在的 SQL 实际在做什么？

用于提供：

```text
SQL summary
business purpose
main tables
output columns
uncertainties
route signals
```

是原子 Executor。

---

## Validation

当前所谓 Validate 实际是一个完整子 Workflow：

```text
Explain
↓
Review
↓
Route
↓
Fix
↓
Re-review
↓
Critic
```

所以它使用：

```text
TrustedSQLWorkflow
```

是合理的。

整个系统其实是：

```text
QueryAgentGraph
    │
    ├─ Planner
    ├─ Generator
    ├─ TrustedSQLWorkflow
    │    ├─ Explain
    │    ├─ Review
    │    ├─ Fix
    │    └─ Critic
    │
    └─ Semantic Validator
```

即嵌套 Workflow。

---

# 九、Metadata 架构

Metadata 是 Shared Physical Truth，不属于 Warehouse Capability。

冻结原则：

```text
Physical Metadata
≠
Semantic Model
≠
Business Knowledge
```

核心 Domain DTO：

```text
ColumnMetadata
TableMetadata
TableLookupResult
```

不要再新增：

```text
MetadataSnapshot
MetadataTableSnapshot
MetadataColumnSnapshot
```

作为公共 Domain Model。

---

## 9.1 SQLite

SQLite 是持久化事实库。

Runtime：

```text
只读
不 initialize
不 import Excel
不 rebuild
```

Import / Rebuild 是维护流程。

---

## 9.2 一个物理字段只保留一个主描述

用户已经明确否决：

```text
同一字段维护多个历史中文描述
→ alias 主模型
```

原则：

> 一个物理表 / 字段只保留一个主中文描述。

历史漂移不成为当前 Physical Truth 的主结构。

---

## 9.3 当前新发现的 Metadata 三态问题

这是下一窗口的重点。

当前 Excel import 对：

```text
is_partition
```

没有事实时写：

```text
NULL
```

这是正确的：

```text
UNKNOWN
```

但当前 Runtime Repository 会：

```text
NULL
→ 没有 partition field
→ ()
→ bool(()) = False
```

最终 Reviewer 收到：

```text
Is Partitioned: False
```

于是：

```text
UNKNOWN
被错误转换成
FALSE
```

这在最新实际运行中已经暴露。

当前运行中 Query Context 明确认为：

```text
dt = 数据报送日期分区字段
```

而 Physical Metadata 给 Reviewer：

```text
Is Partitioned: False
Partition Fields: None
```

同时物理字段描述中：

```text
is_high_tech_mfg_loan_code
= 是否高技术制造业贷款代码
```

而 Business Knowledge 当前认为：

```text
is_high_tech_mfg_loan_code='1'
= 高新技术企业贷款
```

这说明已经进入：

> **Physical Metadata 与 Business Knowledge 的事实一致性治理阶段。**

最新日志已经证明 Query Context 能完整进入 Reviewer，同时最终仍为 `context_required`。

---

# 十、Text-to-SQL 当前架构

```text
TextToSQLCapability
 ↓
QueryAgentGraph
 ↓
Retrieve Context
 ↓
QueryContext
 ↓
Planner
 ↓
Generator
 ↓
TrustedSQLWorkflow
 ↓
Semantic Validator
 ↓
Trusted SQL / Clarification / Failure
```

---

## 10.1 Factory 最新设计

本轮用户明确指出：

> `text_to_sql_factory` 参数过多，尤其 Metadata 配置重复、混乱。

已经完成方向收口：

```text
text_to_sql_factory
→ Context
→ Planner
→ Generator
→ QueryAgentGraph
```

不再负责：

```text
metadata_provider_factory
max_sql_retries
SQL Core 内部构造
```

`trusted_sql_workflow` 应作为已经组装好的依赖注入。

即：

```text
SQL Core Factory
→ Metadata
→ Review
→ Fix
→ LLM
→ Trusted SQL Workflow

Text-to-SQL Factory
→ 注入 trusted_sql_workflow
```

最新 `20260824-7` 已实施这一减肥方向，`20260824-8` 在此基础上继续修复 Review Context。

---

## 10.2 Mandatory Rules

Mandatory Rule 不依赖 Vector Top-K。

目前贷款领域示例：

```text
本期
→ dt = '${p_month_yyyymm}'
```

由：

```text
MandatoryRuleMatcher
```

在 QueryContextBuilder 阶段确定性注入。

Generic Text-to-SQL Factory 不应该认识：

```text
LOAN_MANDATORY_RULES
```

Domain / Demo 自己构建：

```text
QueryContextBuilder(
    mandatory_rule_matcher=...
)
```

然后注入 Factory。

---

# 十一、时间语义的最新决策

历史评估曾认为：

```text
同比 / 环比缺时间
→ clarify
```

但后续已经修改这一策略。

当前：

```text
本期 / 当期 / 当前期
→ ${p_month_yyyymm}
```

是合法 Runtime Convention。

因此：

```text
统计本期高新技术企业贷款余额
```

不应 Clarify。

同比 / 环比如果已经有 authoritative runtime period，可以基于：

```text
${p_month_yyyymm}
```

推导上期或上年同期。

不要机械沿用旧 Golden 的“必须 clarify”。

只有真正存在：

```text
多个 materially different business meanings
```

才 Clarify。

---

# 十二、Evaluation 历史与当前状态

历史 Text-to-SQL V1 曾达到：

```text
12 / 14
85.7%
```

Trusted SQL 当时：

```text
100%
```

历史两类失败主要是：

* 多业务主题歧义；
* 时间语义缺上下文。

但后来进行架构 Consolidation 后出现明显 Regression。

曾经的 11 Case 非绿色测试：

```text
planning 11/11
clarification 11/11
SQL trust 0/11
```

其中：

```text
10 context_required
1 blocked
```

这说明：

> Planning / Context / Generation 大体工作，但 Trusted SQL Gate 产生了严重回归。

历史 Reviewer 独立 A/B 已经看到典型问题包括：

```text
LLM_AGG_GRANULARITY
LLM_FILTER_CODE_VALUE
LLM_PARTITION_DATE
LLM_PERF_SCAN_RANGE
```



---

# 十三、最近这轮回归排查的完整结论

这是下一位 AI 接手后最重要的历史。

## 阶段 1：Generator Markdown Fence

真实 LLM 曾生成：

````text
```sql
SELECT ...
```
````

SQLGlot 没报 parse error，但错误解析成：

```text
Statement Type = column
Source Tables = None
```

Plain/Fenced A/B 已确认。

后来 Generator 增加只剥离完整外层 Fence 的窄 normalization。

最新日志中 Generated SQL 已经恢复为正常纯 SQL。

---

## 阶段 2：发现 Reviewer 没有 QueryContext

旧日志显示：

```text
## Query Context
未提供
```

最终发现历史原因不是简单“删掉了一行”。

旧 Text-to-SQL 通过时：

```text
LLM Review 默认没有作为前置 Trust Gate
Semantic Validator 在后面消费完整 QueryContext
```

后来：

```text
LLM Reviewer
```

被升级成 Trusted SQL 的正式 Gate，却没有同步升级 Validation Input Contract。

因此形成 Integration Regression。

---

## 阶段 3：Context 传递最终修复

最终链：

```text
QueryAgentState
→ TrustedSQLWorkflow
→ SQLReviewRequest
→ SQLExecutionContext
→ ReviewService
→ review_sql
→ run_llm_review
→ LLMReviewer
```

曾经最后一个实际 Bug 是：

```python
review_sql()
→ run_llm_review(...)
```

漏掉：

```python
query_context=query_context
```

最新 commit `20260824-8` 已补齐，并增加专门回归测试：

```text
tests/test_review_service_context.py
```

---

## 阶段 4：Context 已经通，但仍然 context_required

最新实际运行已经确认：

Reviewer Prompt 中已经完整出现：

```text
User Question
Semantic Knowledge
Business Knowledge
Verified SQL Knowledge
```

因此：

> **Context 传递问题现在已经 CLOSED。**

但最后：

```text
validation_status = context_required
```

仍然存在。

这意味着当前真正问题已经转移到：

> **Reviewer 拿到完整 Context 后，为什么仍然产生 context_required Issue。**

---


# 十七、业务知识资产的长期发展方向

已经形成过正式的元数据资产盘点方案，其核心方向正确：

```text
Physical Metadata
↓
Semantic Model
↓
Business Knowledge
↓
Verified SQL
```

而不是：

> 把全部字段描述直接塞给 LLM。

长期业务资产分层建议：

### P0

* Table Business Semantics
* Metrics
* Fixed Filter Rules
* Time Semantics
* Key Dimensions

### P1

* Term / Alias
* Value Dictionary
* Business Topics
* Recommended Usage

### P2

* Join Knowledge
* Grain / relationship
* More complex modeling semantics

当前资产建设方案仍是：

> 先稳定系统主能力，再扩大知识资产覆盖。

此前正式盘点方案也明确记录：物理全量字段本身不足以支撑准确 Text-to-SQL，需要逐步补充 Metric、Filter、Time、Alias、Join 等业务语义资产。

---

# 十八、后续路线

当前主线建议：

```text
P0
Current Reviewer Regression
↓
恢复 Text-to-SQL Trusted SQL baseline
↓
Evaluation V2
↓
确认新 V1 baseline
```

之后：

```text
SQL Optimization V0.2
↓
Knowledge Grounding / Semantic Asset
↓
Narrow Warehouse Development
↓
Skill / Tool / Capability Foundation
```

Optimization 的原则已经确定：

```text
Trusted SQL
↓
Optimization Candidate
↓
Deterministic Re-review
↓
Semantic-equivalence Critic
↓
PASS → Candidate
FAIL → 原 Trusted SQL
```

Optimization 永远不能降低 Trusted SQL 的可靠性。

---

# 十九、下一窗口第一轮建议怎么开始

建议下一 AI 开场直接做这件事：

### 第一步

确认 GitHub HEAD 是否仍是：

```text
20260824-8
d1f79c5...
```

若用户没有继续 push，可以直接基于当前交接继续，不必重新全仓扫描。

### 第二步

让用户运行或读取最新：

```text
reviewer.response
```

不要再改 Context。

### 第三步

把 Reviewer Issues 分成：

```text
已被 QueryContext 证明
已被 Physical Metadata 证明
真实缺失
上下文冲突
纯 Advisory
错误 context_required
```

### 第四步

只修经过验证的根因。

### 第五步

运行：

```text
focused tests
pytest -q
real LLM single case
Evaluation V2
```

必须有真实输出后再宣布通过。

---

# 二十、本轮对话中用户的重要要求

这些要求值得下一 AI 特别记住。

## “为什么以前通过，现在优化架构后反而不通过？”

用户不接受：

> “现在没功能，那我们再加一个。”

必须追历史：

```text
旧能力为什么能工作
↓
架构变化改变了什么
↓
哪一个 Contract 没同步升级
```

本轮最终确认：

> LLM Review 被升级为 Trusted SQL 前置 Gate，而 Context Contract 没同步扩展，是 Regression 的重要来源。

---

## “一个 Context 为什么要搞那么复杂？”

用户明确否决：

```text
ReviewContext V2
FixContext
Context Projection
Inheritance
多份内容
```

核心原则：

> **一个 Context 构建一次，传给所有需要它的接口。**

软件层级可以存在 Request / ExecutionContext，但不能变成第二套业务 Context。

---

## “为什么你不先看看 QueryAgentState？”

这是本轮重要教训。

下一 AI 在提出：

> “应该把 X 放 State”

之前必须先检查：

> State 里是不是已经有 X。

本轮其实：

```text
query_context
```

早就在 `QueryAgentState` 中。

前面没有检查代码就提出重新设计，是错误方法。

---

# 二十一、主开发 AI 的自我反思与后续禁区

本轮出现过多次不应重复的问题。

## 21.1 过早给方案，没有先验证

曾出现：

```text
看到 context_required
↓
猜 Context 没有
↓
马上设计修改
```

而没有先逐级确认：

```text
State
Workflow
Request
Engine
Service
Reviewer
```

之后才发现真正遗漏只是某一层的一行参数。

以后必须先链路验证。

---

## 21.2 把简单 Context 流设计复杂

曾提出：

```text
ReviewTaskContext
projection
render_review_context
SQLExecutionContext 包装更多层
```

用户及时纠正：

> 为什么不直接一个 Context 传给所有接口？

后续禁止重新回到多 Context 架构。

---

## 21.3 没有先看已有 State / Contract

在讨论是否加入 `QueryContext` 时，没有第一时间确认：

```text
QueryAgentState
```

实际上已经有该字段。

这导致重复设计。

以后：

> **先读现有 Contract，再提出新 Contract。**

---

## 21.4 一次给出太多修改，掩盖真实根因

曾经为一个 Context Bug 同时建议修改：

* Graph；
* Workflow；
* Request；
* ExecutionContext；
* Engine；
* Review；
* Fix；
* Prompt；
* Factory；

结果用户修改很多以后行为没有变化。

真正最后一层只是：

```python
query_context=query_context
```

漏掉。

以后必须：

```text
找到第一个 value 正确的位置
↓
找到下一个 value 变成错误的位置
↓
只修断点
```

---

## 21.5 没有提前增加可观测性

Reviewer 正常返回的 JSON 没有 DEBUG 输出。

于是：

```text
context_required
```

只能猜原因。

最新 `20260824-8` 已补：

```text
reviewer.response
```

以后复杂 Agent 调试原则：

> **首先让中间状态可见，再修改算法。**

---

## 21.6 把 UNKNOWN 当成 FALSE

Metadata 领域尤其要严格：

```text
不存在
≠
未知
≠
查询失败
```

类似：

```text
partition unknown
```

绝不能自动转换成：

```text
not partitioned
```

这一点与此前：

```text
FOUND
NOT_FOUND
ERROR
```

三态原则完全一致。

---

# 二十二、最终冻结规则清单

下一 AI 应把下面视为当前项目的硬约束：

```text
1. Text-to-SQL 最终产物是 Trusted SQL，不以真实执行作为当前 Gate。

2. SQL Analysis 使用 SQLGlot + Thin Adapter + Own DTO。

3. QueryAgentGraph 是 Text-to-SQL 唯一 canonical runtime。

4. 一个 User Turn 只有一个 QueryContext。

5. QueryContext 构建一次，所有下游共享，不重新 RAG。

6. QueryAgentState 持有 QueryContext。

7. TrustedSQLWorkflow 可在边界接受 QueryContext，但不能依赖 QueryAgentState。

8. SQLExecutionContext 是运行容器，不是第二套业务 Context。

9. Physical Metadata / Semantic Model / Business Knowledge 必须分层。

10. SQLite 是 Metadata Physical Truth，Runtime 只读。

11. 一个物理表/字段一个主中文描述。

12. Issue.action 是 Trusted SQL 路由事实源。

13. LLM 不得 BLOCK。

14. Fix 必须 Re-review，再 Critic。

15. 重大架构调整先讨论后实现。

16. Debug 先验证根因，再修改。

17. 不为了抽象而增加 BaseService / Universal DTO / Universal Framework。

18. 默认不反复扫描 GitHub。

19. 测试通过必须有实际 pytest 输出，不可口头假定。

20. 当前不要继续调整 Context 架构；优先解决 Reviewer 为什么在完整 Context 下仍返回 context_required。
```

---

# 二十三、当前交接状态一句话总结

截至 **2026-08-24 / commit `20260824-8`**：

> **Trusted SQL 主架构、Text-to-SQL Graph、单一 QueryContext 架构、Factory 分层、Context 到 Reviewer 的传递已经基本收口；当前真正的 P0 不再是“Context 没传过去”，而是“Reviewer 在已经拿到完整 Context 后仍然产生 `context_required`”。下一步必须读取新增的 `reviewer.response` 原始 Issue，结合 Physical Metadata 与 Business Knowledge 的冲突逐项验证，不允许再凭状态码猜根因。**

这就是下一窗口应直接接手的位置。




1. **GitHub 当前是不是完整事实源？**
   `20260824-8` 以后，你本地还有没有**尚未 push** 的代码修改？如果有，我之后的“全仓逐行审计”只能以 GitHub 为基准，同时把本地差异标为未知；如果没有，我就冻结 `d1f79c5...` 为本轮 Baseline。

2. **V1 最终到底是一个什么产品形态？**
   我已经知道四项 V1 能力是 Trusted SQL、Text-to-SQL、窄版数仓开发、Agent/Skill/Evaluation。现在缺的是最终使用方式：你希望 V1 首先成为
   **A. 一个可运行的 Python DataAgent 内核/SDK**，
   **B. 一个可以通过 API 被业务系统调用的后端服务**，
   还是 **C. 先形成完整技术能力，界面/API 产品化以后再做**？
   **我的倾向是 C → A，再 API 化。**当前仓库本质仍然是 Python Engine/Capability，而不是服务产品，没必要现在引入 Web/API 层。

3. **V1 的主要业务用户是谁？**
   是你自己/数据开发人员，用自然语言完成 SQL 和数仓开发；还是普通业务人员直接问数？这个区别很大。前者可以接受更多技术状态和人工确认，后者必须把 Metadata、澄清、错误恢复隐藏得更多。

4. **V1 是否明确以 MaxCompute / DataWorks 为第一生产目标？**
   当前项目虽然 SQLGlot 提供多方言能力，但工程描述、Rule、Prompt、Metadata 和真实案例明显都是 MaxCompute/DataWorks 导向，`pyproject.toml` 甚至仍描述为 “SQL Review Engine for MaxCompute / DataWorks”。
   **我的建议：架构保持 dialect 可扩展，但 V1 验收只针对 MaxCompute。**不要为了所谓通用 DataAgent 同时兼容 MySQL/PostgreSQL/Spark SQL。

5. **Trusted SQL 是不是整个 V1 的“公共底座”，而不是 Text-to-SQL 私有步骤？**
   我认为答案应该是“是”。也就是说未来：
   `Text-to-SQL → Trusted SQL`
   `Warehouse Development → Trusted SQL`
   `SQL Optimization → Trusted SQL`
   都复用同一个 SQL Core，而不是各写一套 Validator。当前 `TrustedSQLWorkflow` 已基本符合这个方向。
   如果你同意，我会把这作为正式冻结原则。

6. **生产态 Trusted SQL 中，Physical Metadata 到底是不是强制依赖？**
   这是一个必须现在确定的架构决策。当前 `build_trusted_sql_workflow()` 默认是 `default_enable_metadata=False`。
   但如果我们宣称“可信 SQL”，我认为生产 Text-to-SQL 下至少涉及真实业务表时，**Metadata 应当默认启用**。否则字段是否存在、数据类型等物理事实无法真正验证。测试和纯 SQL Review 可以显式关闭。
   你是否接受这个方向？

7. **Metadata 不知道某个事实时，希望系统如何处理？**
   我认为必须正式确立三态甚至多态：
   `TRUE / FALSE / UNKNOWN`，
   `FOUND / NOT_FOUND / ERROR`。
   例如“Excel 没告诉我们 dt 是不是分区字段”，绝不能理解成“dt 不是分区字段”。当前代码恰好违反了这一点。
   这里我倾向把“事实未知”传递到底，而不是让 Reviewer 猜。

8. **当 Physical Metadata 与 Business Knowledge 冲突时，谁有最终解释权？**
   当前真实案例已经出现这种情况，所以不能拖到以后再定。我的建议是建立明确 Authority，而不是简单说“谁优先级高”：

   * 表/字段存在、字段类型、真实物理分区 → **Physical Metadata**；
   * 指标定义、代码值业务含义、业务过滤条件、时间语义 → **Business/Semantic Knowledge**；
   * 本次用户选择/澄清 → **Session Context**，只能改变业务意图，不能修改物理事实；
   * Verified SQL → 参考证据，不能覆盖上述权威事实。
     你是否认同？如果不认同，需要指出例外。

9. **“一个 Turn 只有一个 QueryContext”需要再精确定义一次。**
   当前 `QueryContext` 是 `frozen=True`；正常链路确实同一个对象进入 Planner、Generator、Trusted SQL Workflow 和 Semantic Validator。
   但用户回答澄清问题以后，当前 Graph 会把答案加入 `session_context`，然后重新经过 `retrieve_context`，**生成一个新的 QueryContext**。
   我认为这是合理的：**一次“上下文快照”一个 QueryContext；HITL 增加了新事实以后必须重建快照，但禁止每个下游消费者各建自己的 Context。**
   你是否接受这个更精确的定义？

10. **`ReviewContext`、`SQLExecutionContext` 这类名字是否允许保留？**
    它们不是第二份业务 Context。`ReviewContext` 保存 AST/SQLFacts/MetadataProvider 等 SQL Review 技术状态；`SQLExecutionContext` 保存 SQL Core 本次执行参数，并引用同一个 QueryContext。
    **我的判断是应该保留这种技术上下文，禁止的是第二套业务知识 Context。**否则为了“只允许一个叫 Context 的类”反而会破坏合理的软件分层。你是否认可？

11. **LLM Reviewer 与 SemanticSQLValidator 的职责要怎么切？这是当前最重要的架构问题之一。**
    现在 Reviewer 的 Prompt 明确检查“指标口径、业务过滤、时间语义、SQL业务语义一致性”；而后面的 `SemanticSQLValidator` 又检查“正确表、指标、过滤、时间、聚合、完整回答问题”。两者存在明显重叠。
    我的初步方向是：
    **Trusted SQL Reviewer** 负责“这段 SQL 本身是否可靠/安全/合理，以及基于已有上下文可发现的 SQL 风险”；
    **Semantic Validator** 专门负责“这段可信 SQL 是否完整实现了这次 QueryPlan / 用户意图”。
    也就是 `SQL correctness/trust` 与 `task fulfillment` 分开。
    你是否认同？这个确认以后我才会判断当前 `context_required` 到底应该在哪一层产生。

12. **`context_required` 的权限边界是否要收紧？**
    我不建议继续允许 Reviewer 只因为“它自己不确信”就输出 `context_required`。如果 QueryContext 已经有权威答案，它就不能再次追问；只有**确实缺失、且不同答案会生成 materially different SQL** 时才能要求上下文。当前 Prompt 已经试图表达这条原则，但还没有形成足够严格的程序 Contract。
    是否把它设为正式规则？

13. **Clarification 最终是 Planning 的责任，还是所有阶段都允许发起？**
    当前 Planner 可以 Clarify，Semantic Validator 也可以 Clarify，Trusted SQL Reviewer 还能产生 `context_required`。这意味着有三个入口。
    我的倾向不是强行只留 Planner，而是：底层发现缺失 → 返回结构化 Missing Context；**真正对用户发起 HITL 统一由 QueryAgentGraph**。这样各层发现问题，但 Runtime 拥有用户交互。你是否接受？

14. **你对“窄版数仓开发”的具体定义现在必须补全。**
    “单目标表”我知道，但它还不足以设计架构。你期待它能做到哪些步骤？比如：
    `需求理解 → 源表发现 → 字段映射 → 目标表 Schema → ETL SQL → SQL 校验 → 建表 SQL/任务代码`，
    还是只做到其中一部分？
    这是我现在最缺的一块产品定义，因为它决定未来是否复用 QueryAgentGraph、QueryContext、Planning，以及是否需要新的 Warehouse Workflow。

15. **窄版数仓开发是否同样“不执行，只产出可信代码”？**
    Text-to-SQL 已经明确最终交付 Trusted SQL，不以数据库真实执行为 Gate。
    我倾向 V1 的数仓开发也采取类似原则：产出经过静态与语义验证的 DDL/DML/ETL SQL，不要求真正向 DataWorks 发布。请确认。

16. **Semantic Model 到底是“人工治理资产”还是未来要由系统自动生成/维护？**
    当前代码把它作为 JSON/领域代码加载，但运行时每次都会渲染进入 Context。
    如果未来你希望“导入全量 Metadata → LLM 辅助生成 Semantic Assets → 人工审核 → 发布”，那我们现在设计资产层时就要保留这个生命周期；如果永远手工写 JSON，则没必要提前建设复杂管理系统。

17. **Business Knowledge / Verified SQL 的持久化与发布机制是否属于 V1？**
    当前 Text-to-SQL Factory 会建立 Vector Store，并在 Capability 构建时 `vector_store.add(context_documents)`。
    我认为这个方式适合当前实验，但不适合最终 Runtime：**知识导入应该和查询 Runtime 分开**，类似你已经对 Metadata 做的 rebuild/runtime separation。
    你是否希望在 Text-to-SQL baseline 稳定后，把 Knowledge Asset 也改成“离线构建、运行时只读”？

18. **贷款领域是否就是当前 V1 的唯一 Golden Domain？**
    当前 V2 Evaluation 已经围绕科技贷款、绿色贷款、余额、获贷企业数、加权利率、地区、机构类型和歧义澄清建立案例。
    我的建议是先把这个 domain 做到稳定，而不是立即增加更多行业。等平台能力稳定后再测试第二个 domain，验证架构是否真的泛化。

19. **Evaluation 的正式通过标准是什么？**
    不能再只说“跑过了”。我建议下一版冻结至少四个 Gate：
    `Deterministic/unit tests 100%`

    * `Text-to-SQL Golden Cases`
    * `Trusted SQL Gate`
    * `真实 LLM 重复稳定性`。
      特别是 LLM 不是确定性函数，一次 100% 不代表系统稳定。你是否愿意把“关键 Golden Case 连续多轮通过”纳入 V1 Gate？如果担心 API 成本，可以只对核心 Case 做重复测试。

20. **你希望 Evaluation 更看重“最终 SQL 正确”，还是每个中间 Stage 也必须匹配？**
    例如最终 SQL 正确，但 Planner 把某个 requirement 放进 `filters` 而不是 `requirements`，是否算失败？我的建议是：

    * 中间 Contract 只验证影响下游的关键语义；
    * 最终 SQL correctness / semantic fidelity 权重最高；
    * 不为了固定 LLM 的“思考格式”过度约束中间结果。
      请确认。

21. **LangGraph 是否正式冻结为 Text-to-SQL Runtime？**
    现在已经不是简单试验：HITL `interrupt/resume`、Checkpoint、Retry、State 都依赖 LangGraph。
    我目前**不建议再退回普通 Python Workflow**。除非全仓审计发现严重理由，否则应该把 LangGraph 定为 Agent Runtime 基础设施。你是否同意？

22. **未来的 Agent Runtime 是“每个 Capability 一个 Graph”，还是最终有一个顶层 Agent 再选择 Capability？**
    这会直接决定未来 Skill/Tool 架构。我倾向于：
    `Top-level Agent Runtime / Planner`
    → 选择 `TextToSQLCapability / WarehouseCapability / SQLReviewCapability / ...`
    → 每个复杂 Capability 可以有自己的内部 Graph。
    而不是做一个超级 LangGraph，把所有业务节点都塞进一张图。你对此有无产品设想？

23. **Skill 与 Tool 在你的项目里最终分别是什么？**
    这是目前四个 V1 目标中定义最薄的一块。我的理解候选是：

    * Tool：确定性/外部能力，例如 Metadata Search、SQL Analysis、未来 DataWorks API；
    * Skill：面向任务的可组合知识+流程，例如“字段命名”“数仓表设计”“贷款指标查询”。
      但这个定义不能由我自行冻结，需要你告诉我你期待的 Skill 产品形态。

24. **LLM 供应商是否必须可替换？**
    当前实际主模型是 DeepSeek，但代码已经抽象 Client / TextGenerationModel。我的建议是：**V1 运行基准用 DeepSeek，架构保持 Provider 可替换，但不为了多模型兼容制造额外框架。**你是否同意？

25. **生产 Observability 要到什么程度？**
    现在新增 `reviewer.response` DEBUG 非常有利于 Debug，但以后 QueryContext、SQL、业务规则乃至内部表名都可能属于敏感资产。
    我建议区分：
    `dev/debug：完整 prompt/response`
    `prod：trace + stage + status + token/latency + 脱敏摘要`。
    是否需要把 Observability 当成 V1 平台基础能力的一部分？

26. **Repository 本身要不要纳入这轮治理？**
    当前 `.gitignore` 已经明确忽略 `__pycache__ / *.pyc / *.egg-info / .DS_Store`，但仓库历史上仍实际跟踪了这些文件；根目录也直接提交了 7MB 左右的 `agent_metadata.db`。
    我的建议是全仓审计里把**代码卫生、死代码、重复文件、生成物、资产文件管理**一起处理，而不只找功能 Bug。否则“胡拼乱凑感”很大一部分正是从这些技术债开始积累的。

27. **Metadata SQLite DB 是否计划长期提交进 Git？**
    这里需要你给产品/部署意图，而不是让我按通用 Best Practice 猜。如果它只是本地生成物，我会建议移出版本库，仅保留 Schema + source + rebuild；如果它是一个经过审核的版本化 Metadata Snapshot，则可以继续纳入，但需要明确版本与更新策略。

28. **我以后是只给你修改指导，还是在你明确授权时也可以直接修改 GitHub？**
    我现在对仓库有写权限，但在没有你明确要求的情况下，我不会写。结合你的开发学习目标，我倾向继续：
    **我逐行审查 → 给文件/位置/原因/修改代码 → 你修改和运行 → push 后我复核**。
    大型测试文件可以给完整代码。你是否继续采用这个方式？

29. **这次全仓扫描的范围是否包括“历史兼容代码是否还应该存在”？**
    例如当前 `ReviewService.review()` 明确写着新入口，而 `review_sql()` 因旧调用方和旧测试继续保留。
    我建议这次不仅判断“代码能不能跑”，还要分类：
    **Canonical / Compatibility / Deprecated / Dead Code / Future Placeholder**。
    只有这样才能真正判断是否已经产生新旧架构混杂。你同意的话，我会把它纳入扫描标准。

30. **最后，需要你给我两个真实运行事实。**
    GitHub 只能告诉我代码是什么，不能告诉我 DeepSeek 今天实际返回了什么。等你回答完架构问题后，我需要：
    **当前 HEAD 的最新 `pytest -q` 完整结果**，以及那条“本期高新技术企业贷款余额”的**最新真实运行输出，尤其 `reviewer.response`**。
    这两个不是让你现在解释原因，只是后续代码审计完成后用于和 Runtime Reality 对齐。

1. github为最新；2. C; 3. 先面对我自己；4. 以dataworks为主导；5. 我考虑agent的主要产出是trusted\_sql，但是应该还有其他更多样式才对；6. llm和metadat默认开启；7. 建立多态吧；8. 我觉得本来这两部分内容就不应该冲突，如果冲突的话我觉得进入clarify，有session确定；9. 这就在于怎么定义querycontext了，我之前对它的定义就只是固定的业务知识，包含semantic\_model knowledge fix\_rule session\_text等，它只跟用户的提问内容有关，跟哪个环节和能力无关。你是怎么考虑的呢？10. 命名不规范的，你提出方案修改就行；11.我认同你的分工，但是你需要再确认下；12. 设立；13. 我觉得都允许发起clarify，我觉得humaninloop非常重要；14. 我觉得这个步骤还是太长了，先放到最后面实现，但是所有步骤我觉得都要做到，形成端到端；15. 所有代码目前都不考虑执行；16. 我觉得smantic\_model应该是人机协同整理的资产，你觉得呢？17. 先考虑只读吧；18. 不，我的业务非常多，但目前我更需要的是稳定我的dataagent产品，而不是业务和数据；19. 对核心case做重复测试；20. 按你的建议来；21. 同意；22. 按你倾向来，你如果不确定，参考业界常用架构；23. 这部分先不考虑，我后面再补充需求；24. 可替换；25. 这部分不着急吧，等建设完整再设立？26. 一起处理吧；27. 长期提交git；28. 继续采用；29. 我觉得旧架构要清理了，就只保留干净的新架构；30. FAILED tests/test\_query\_agent\_graph\_hitl.py::test\_graph\_interrupts\_and\_resumes - TypeError: PassingTrustedSQLWorkflow\.run() got an unexpected keyword argument 'query\_context'

   FAILED tests/test\_query\_agent\_graph\_semantic.py::test\_semantic\_pass\_produces\_trusted\_sql - TypeError: PassingTrustedSQLWorkflow\.run() got an unexpectedkeyword argument 'query\_context'

   FAILED tests/test\_query\_agent\_graph\_semantic.py::test\_semantic\_fail\_retries\_then\_passes - TypeError: PassingTrustedSQLWorkflow\.run() got an unexpected keyword argument 'query\_context'

   FAILED tests/test\_query\_agent\_graph\_semantic.py::test\_deterministic\_block\_stops\_before\_semantic\_validation - TypeError: FailingTrustedSQLWorkflow\.run()got an unexpected keyword argument 'dialect'

   FAILED tests/test\_query\_agent\_graph\_semantic.py::test\_semantic\_need\_clarification\_interrupts - TypeError: PassingTrustedSQLWorkflow\.run() got an unexpected keyword argument 'query\_context'

   FAILED tests/test\_sql\_review\_factory.py::test\_factory\_disables\_metadata\_without\_provider - assert False

   FAILED tests/test\_to\_sql\_service.py::test\_text\_to\_sql\_pipeline\_returns\_trusted\_sql - TypeError: build\_text\_to\_sql\_capability() got an unexpected keyword argument 'max\_sql\_retries'

   FAILED tests/test\_to\_sql\_service.py::test\_text\_to\_sql\_pipeline\_blocks\_dangerous\_sql - TypeError: build\_text\_to\_sql\_capability() got an unexpected keyword argument 'max\_sql\_retries'

   8 failed, 34 passed in 4.53s。 

上述内容，是一份交接文档，你需要阅读上述所有内容，并对这份项目进行一次技术分析，不需要完成交接文档里的工作内容。1.我希望你能够通过逐行扫描github代码的方式，确认我目前项目的进度、问题、方向等情况，文档内容仅作参考；2. 你要从一开始就确定我的项目后续的工作方案和具体方向，与我确认好技术架构；3.  现在请你先对我的项目、方案、内容提出你应该有的问题，以让你充分了解我的需求


A. 元数据事实源（最关键，其余都依赖它）
data/metadata/raw/全量字段.xlsx 到底是什么？ 是 MaxCompute 真实 DDL 导出，还是业务报送口径的字段清单？它有没有数据类型列、分区标识列，只是导入代码没读？还是源文件本身就没有？
你能否拿到真实的物理 Schema？（DESC 导出 / DataWorks 元数据 API / information_schema）如果能，V1 应该以它为准，Excel 降级为业务描述补充；如果不能，我们必须承认「类型和分区永远 UNKNOWN」，Trusted SQL 的判定标准要相应下调。
ods_hd_100_cldkxx 的真实粒度是什么？ 它到底是借据明细，还是已经按 field_type_code 聚合的报送表？这个答案决定 COUNT(DISTINCT ent_code) 和加权利率这两个指标能不能成立——目前物理表里已经有 loan_ent_num 和 loan_rate 现成聚合列。
这是我整理的字段清单，没有收集其他信息，可以收集，但要额外费时间，且不是我目前的工作重点，我现在的工作重点应该是先完成整个平台的搭建，目前这些数据能够充分验证我的功能我觉得就可以了。


B. 知识资产
loan_model.json 是你按真实业务写的，还是为了跑通 Demo 编的？ 我需要知道它是「待修正的资产」还是「待丢弃的脚手架」。
如果 ods_hd_100/200_cldkxx 不是你真正要查的表，真实场景应该指向哪一批？库里有 ads_js_201_cldwdk_gx_v3(市场处_存量单位贷款_高新技术企业)、ads_rh_scc_bb_cldwdk_gx_v3 等一批明显更贴近的表。你希望 V1 的 Golden Domain 建在 ODS 还是 ADS 上？
is_high_tech_mfg_loan_code：物理说「高技术制造业」，你的业务规则说「高新技术企业」——哪个对？ 这是你第 8 条回答「本来就不应该冲突，冲突就 clarify」的第一个实战样本。如果这类冲突源自 Semantic Model 写错，那它就不该走 clarify，而该走资产修正。我需要你确认：冲突的默认处理是"问用户"还是"标记为资产缺陷、阻断并报告"？
这些冲突跟上面回答理解一样

C. Trusted SQL 门槛
在 data_type 全部 UNKNOWN 的现状下，你接受什么样的 Trusted SQL 定义？ 我倾向：表存在 + 字段存在 + 无危险操作 + 分区已限定 + 指标口径与已声明业务规则一致 = Trusted；类型相关的检查在 UNKNOWN 时降级为 advisory 而非 context_required。你认可吗？
可以

Generator 要不要拿 Metadata？ 我强烈建议要（按 Plan 命中的表注入字段清单）。但这会让 Generation Prompt 变大——build_metadata_context_text 现在是全表字段无裁剪 dump，ods_hd_100_cldkxx 有 33 个字段（含 10 个 backup），别的表可能上百。你接受我引入一个「按 Plan 裁剪字段」的机制吗？这算是新增模块，按规矩我先问。
我觉得裁剪字段会不会使得元数据内容丢失呢？你可以做个判断

Reviewer 的 context_required 要不要接 HITL？ 接的话，Reviewer 必须输出结构化 missing_context（当前 Schema 里没有这个字段，需要扩契约）。你确认要扩吗？
扩

D. 清理范围
你第 29 条说「旧架构清理，只保留干净的新架构」——我按这个标准，standards/ 整包、旧 evaluation 三件套、旧 examples eval、根 cli.py、temp.md、handoff/、docs/ 是否全部删除？ 特别是 handoff/ 和 docs/ 里有 4 份互相矛盾的历史文档，我建议全删只留一份 ARCHITECTURE.md。你确认吗？
把你觉得需要更新和清理的内容列个方案，哪些需要清理，怎么清理给我

.pyc / .DS_Store / egg-info 需要从 Git 历史中移除（git rm --cached），这会产生一个大 commit。你接受吗？
可以

agent_metadata.db 你说长期提交 Git。 那我需要一个版本策略：每次 rebuild 都提交 7MB 二进制会让仓库快速膨胀。我的建议是保留提交，但配套 metadata_build_info 里记录源文件 hash + 构建时间，并约定「只在源 Excel 变化时重建」。你认可吗？
可以

E. 工作方式
第一阶段你希望我先做哪个？
(a) 先修 8 个红灯 + 建测试基础设施（1 轮，见效快，让 baseline 变绿）
(b) 先做元数据事实层对齐（最根本，但需要你先回答 A 组问题）
我的倾向是 (a) → (b)：先让 pytest -q 全绿，才有资格谈回归。
先a后b

你有没有能力提供一张表的真实 DESC 输出？ 只要一张（比如 ods_hd_100_cldkxx），我就能验证 Excel 与物理 Schema 的偏差程度，从而判断整个元数据资产是「需要补字段」还是「需要重建」。这是我现在最缺的一个 Runtime Reality。
你觉得重要吗？重要的话我完全可以提供，excel基本就是最真实的，semantic是我编造的；

我不仅仅希望你停留在这些方面，我希望你能够充分评价我的项目架构、技术路线和后续的实现情况，为我描述一份完整的技术文档，内容要充分，既要考虑到我自身对产品的需求和定义，也要跟进市场目前dataagent的技术路线，最好还能参考目前pi-agent、harness、claude code等agent的设计俩年。让我能够开展后续工作。












python examples/text_to_sql_eval_v2.py --case explicit_high_tech_month --case high_tech_yoy --repeat 1

python examples/text_to_sql_demo.py --use-real-llm --question "统计2026年7月高新技术企业的贷款余额" --dialect maxcompute --log-level INFO




python examples/text_to_sql_demo.py --use-real-llm --question "统计2026年7月高新技术企业的贷款余额" --dialect maxcompute --log-level INFO


我已将代码git到云端，你可以扫描一遍代码，然后进入下一环节，确保内容要符合我的代码和技术方案

我已经完成上面内容，请你按计划继续往下


沿着技术方案和讨论内容继续下去吧，你最好再考虑下是否有必要做这部分内容并给出解释，说明考虑的点和业界有哪些是可以参考的


git rm -r --cached --ignore-unmatch __pycache__ sqlpilot_review_agent.egg-info

































python examples/text_to_sql_eval_v2.py --case explicit_high_tech_month --repeat 1



你以后提供代码，要给非常详细的注释，参考我给你的样例，甚至要比这个还要详细；2. 你提供代码内容要准确，不要模糊，也不要脱离之前的代码进行修改；3. 你应该要准确解释，为什么添加这个功能要对应修改、按顺序修改这几处地方，而不是只说明修改内容；4. 按之前技术方案继续往下。