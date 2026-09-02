"""
SQL Analysis 包的稳定公共入口。

【架构位置】
Candidate SQL -> SQLParser -> SQLFactsExtractor -> SQLAnalysisAdapter -> Trusted SQL Review。

【为什么存在这个包入口】
上层组件不应该到处记忆 analysis 子模块的内部文件布局，因此这里集中导出稳定 Contract。
后续即使 SQLGlot 适配实现拆分，Rule、Service、Workflow 依赖的公开名称仍可以保持稳定。

【边界】
- 本包只负责从 SQL 中提取客观结构事实，不判断业务语义是否正确；
- 不在这里加入 capability-specific 规则；
- 不重新实现 SQLGlot 的 Parser、Scope 或 Lineage 算法。
"""

from sql_pilot_engine.analysis.sql_parser import (
    SQLParseResult,
    SQLParser,
)
from sql_pilot_engine.analysis.facts import (
    AggregateFact,
    ColumnReference,
    PredicateFact,
    SQLFacts,
    SQLFactsExtractor,
    TableReference,
)
from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
    SQLAnalysisResult,
)

# __all__ 明确本包承诺给外部使用的稳定 API；未列出的内部 helper 不应被上层直接依赖。
__all__ = [
    "SQLParseResult",
    "SQLParser",
    "ColumnReference",
    "SQLFacts",
    "SQLFactsExtractor",
    "TableReference",
    "SQLAnalysisAdapter",
    "SQLAnalysisResult",
    "AggregateFact",
    "PredicateFact",
]
