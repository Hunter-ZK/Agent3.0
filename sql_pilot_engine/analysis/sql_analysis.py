"""
SQL Analysis 的组合适配层：把“解析 SQL”与“提取 SQLFacts”组织成一次稳定分析调用。

【架构位置】
Generated / Candidate SQL
    -> SQLAnalysisAdapter.analyze()
        -> SQLParser.parse()
        -> SQLFactsExtractor.extract()
    -> SQLAnalysisResult
    -> ReviewService / MetadataValidator / Deterministic Rules

【为什么需要 Adapter】
Parser 只负责把 SQL 变成 AST；FactsExtractor 只负责从可信 AST 中提取客观事实。
上层如果分别调用两者，就容易出现重复解析、忘记检查 parse success、或不同规则拿到不同
分析结果的问题。因此本类提供一个非常薄的统一入口，但不在这里增加业务规则。

【边界】
- 解析失败是普通分析结果：facts=None，而不是伪造空 SQLFacts；
- 本层不判断 SQL 是否“可信”，也不决定 IssueAction；
- 本层不重新实现 SQLGlot 的 AST/Scope/Lineage 算法。
"""

from __future__ import annotations

from dataclasses import dataclass

from sql_pilot_engine.analysis.sql_parser import (
    SQLParseResult,
    SQLParser,
)
from sql_pilot_engine.analysis.facts import (
    SQLFacts,
    SQLFactsExtractor,
)


@dataclass(frozen=True)
class SQLAnalysisResult:
    """
    一次 SQL Analysis 的只读结果。

    parse_result 永远存在，因为“是否成功解析”本身就是事实；只有解析成功时 facts 才存在。
    frozen=True 防止后续 Rule 在共享同一 Analysis Result 时修改事实，造成规则顺序依赖。
    """

    # Parser 的原始结构化结果，包含 AST statements、dialect 与错误信息。
    parse_result: SQLParseResult

    # 只有 parse_result.success=True 才能构造 SQLFacts；失败时必须为 None。
    facts: SQLFacts | None

    @property
    def success(self) -> bool:
        """统一暴露解析是否成功，避免上层重复穿透 parse_result。"""

        return self.parse_result.success


class SQLAnalysisAdapter:
    """
    SQLParser 与 SQLFactsExtractor 的薄组合层。

    parser / facts_extractor 支持依赖注入，主要用于测试和未来替换实现；默认使用项目正式实现。
    这里刻意不持有 ReviewContext、MetadataProvider 或 RuleRegistry，因为那些属于更高层职责。
    """

    def __init__(
        self,
        parser: SQLParser | None = None,
        facts_extractor: SQLFactsExtractor | None = None,
    ) -> None:
        # 使用 ``or`` 提供默认组件，让生产代码无需显式组装，同时保留测试替身能力。
        self.parser = parser or SQLParser()
        self.facts_extractor = facts_extractor or SQLFactsExtractor()

    def analyze(
        self,
        sql: str,
        *,
        dialect: str = "maxcompute",
    ) -> SQLAnalysisResult:
        """
        解析 SQL 并在解析成功时提取稳定 SQLFacts。

        参数：
        - sql：待审查的 SQL Candidate；
        - dialect：Agent3.0 产品层方言名，具体 SQLGlot 方言映射由 SQLParser 负责。

        返回：
        - 成功：SQLAnalysisResult(parse_result=成功结果, facts=SQLFacts)；
        - 解析失败：SQLAnalysisResult(parse_result=失败结果, facts=None)。

        解析失败后立即返回是重要安全边界：没有可信 AST 时不能继续做事实推断。
        """

        # Stage 1：统一走 SQLParser，避免各调用方直接依赖 sqlglot.parse()。
        parse_result = self.parser.parse(
            sql=sql,
            dialect=dialect,
        )

        # Stage 2：失败 AST 不允许进入 FactsExtractor；facts=None 明确表示“事实不可得”。
        if not parse_result.success:
            return SQLAnalysisResult(
                parse_result=parse_result,
                facts=None,
            )

        # Stage 3：只从已经成功解析的同一份 AST 中提取事实，保证一次分析内部一致。
        facts = self.facts_extractor.extract(
            parse_result=parse_result,
        )

        return SQLAnalysisResult(
            parse_result=parse_result,
            facts=facts,
        )
