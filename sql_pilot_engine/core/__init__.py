"""
SQL Pilot Engine 的 Core 公共入口。

【架构位置】
Core 位于各 Capability、Workflow、Service 共享的最底层 Domain/Runtime Contract 区域。
它只承载跨能力都成立的通用模型和执行上下文，不放 Text-to-SQL、SQL Review 等能力专属逻辑。

当前对外只稳定导出 SQLExecutionContext。保持较小的公开面可以避免上层代码绕过 Service/Workflow
直接耦合内部模型；后续若需要扩大公共 API，应先确认它确实属于 Shared Core。
"""

from sql_pilot_engine.core.execution_context import SQLExecutionContext


# 显式声明稳定导出，避免 ``from sql_pilot_engine.core import *`` 暴露未来内部 helper。
__all__ = ["SQLExecutionContext"]
