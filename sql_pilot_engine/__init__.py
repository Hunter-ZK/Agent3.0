"""
Agent3.0 / SQL Pilot Engine 顶层 Python 包。

该包本身不承担业务逻辑，只作为各子域的命名空间根节点。项目按照职责进一步拆分为：
- context / semantic / metadata：上下文与事实资产；
- generation / linking：规划后的物理解析与 SQL Candidate 生成；
- analysis / rules / validation / workflow：Trusted SQL Core；
- runtime：Agent 编排、State、HITL、Checkpoint 与 Event；
- capabilities / app / schemas：对外能力与 Composition Root；
- evaluation / observability：横向质量与运行观测。

保持顶层 __init__ 为空业务逻辑，可以避免导入 sql_pilot_engine 时触发 LLM、数据库、LangGraph 等
重量级依赖初始化，也能减少隐式循环依赖。
"""
