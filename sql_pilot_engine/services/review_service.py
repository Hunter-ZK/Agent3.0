# sql_review_agent/services/review_service.py

from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import IssueSource, Severity, IssueAction
from sql_pilot_engine.core.models import Issue, ReviewResult
from sql_pilot_engine.llm.clients import BaseLLMClient
from sql_pilot_engine.llm.context_builder import build_analysis_context_text, build_metadata_context_text
from sql_pilot_engine.llm.errors import LLMAPIError, LLMError, LLMResponseParseError, LLMResponseValidationError
from sql_pilot_engine.llm.review_prompts import build_issues_text
from sql_pilot_engine.llm.reviewer import LLMReviewer
from sql_pilot_engine.rules.registry import RuleRegistry
from sql_pilot_engine.core.execution_context import SQLExecutionContext


from sql_pilot_engine.analysis.sql_analysis import SQLAnalysisAdapter

from sql_pilot_engine.validation.metadata_validator import MetadataValidator


class ReviewService:
    """SQL Review Agent 主编排服务。"""

    def __init__(
            self, 
            rule_registry: RuleRegistry | None = None, 
            llm_client: BaseLLMClient | None = None,
            analysis_adapter: SQLAnalysisAdapter | None = None,
            metadata_validator: (MetadataValidator | None) = None,
        ) -> None:
        self.rule_registry = rule_registry or RuleRegistry()
        self.llm_client = llm_client
        
        self.analysis_adapter = analysis_adapter or SQLAnalysisAdapter()
        
        self.metadata_validator = (metadata_validator or MetadataValidator())
        
        

    def review(self, context: SQLExecutionContext) -> ReviewResult:
        """基于内部执行上下文执行 SQL Review/Fix。

        这是新的内部主入口。旧的 review_sql(...) 暂时保留，避免破坏旧调用方和旧测试。
        """

        if context.fix_sql:
            raise ValueError(
                "ReviewService only accepts review context."
            )
        
        return self.review_sql(
            sql=context.sql,
            file_path=context.file_path,
            mode=context.mode,
            dialect=context.dialect,
            categories=context.categories,
            metadata_provider=context.metadata_provider,
            enable_llm=context.enable_llm,
            llm_provider=context.llm_provider,
            query_context=context.query_context,
        )

    def review_sql(
        self,
        sql: str,
        file_path: str = "<memory>",
        mode: str = "prod",
        dialect: str = "maxcompute",
        categories: set[str] | None = None,
        metadata_provider=None,
        enable_llm: bool = False,
        llm_provider: str = "mock",
        query_context = None,
    ) -> ReviewResult:

        analysis = (
            self.analysis_adapter.analyze(
                sql=sql,
                dialect=dialect,
            )
        )

        parse_result = (
            analysis.parse_result
        )

        if not parse_result.success:
            parse_issue = Issue(
                rule_id=(
                    "SQL_PARSE_ERROR"
                ),
                title=(
                    "SQL 语法解析失败"
                ),
                severity=Severity.HIGH,
                message=(
                    parse_result.error_message
                    or (
                        "Unknown SQL "
                        "parse error."
                    )
                ),
                suggestion=(
                    "请检查 SQL 语法"
                    "及当前方言配置。"
                ),
                evidence=sql[:500],
                category="syntax",
                source=IssueSource.SYSTEM,
                confidence=1.0,
                action=IssueAction.BLOCK,
                auto_fixable=False,
                metadata={
                    "dialect": dialect,
                },
            )

            return ReviewResult(
                file_path=file_path,
                reviewed_sql=sql,
                risk_level=Severity.HIGH,
                issue_count=1,
                issues=[
                    parse_issue
                ],
                analysis_result=analysis,
            )

        sql_facts = analysis.facts

        if sql_facts is None:
            raise RuntimeError(
                "Successful SQL analysis "
                "must contain SQLFacts."
            )

        context = ReviewContext(
            mode=mode,
            dialect=dialect,
            parse_result=parse_result,
            sql_facts=sql_facts,
            metadata_provider=(
                metadata_provider
            ),
            enable_llm=enable_llm,
            llm_provider=llm_provider,
        )

        guardrail_issues = (
            self.rule_registry.run(
                sql=sql,
                context=context,
                categories=categories,
            )
        )

        metadata_issues: list[
            Issue
        ] = []

        if metadata_provider is not None:
            metadata_issues = (
                self
                .metadata_validator
                .validate(
                    facts=sql_facts,
                    provider=(
                        metadata_provider
                    ),
                )
            )

        deterministic_issues = [
            *guardrail_issues,
            *metadata_issues,
        ]

        analysis_context_text = (
            build_analysis_context_text(
                facts=sql_facts,
                dialect=dialect,
            )
        )

        metadata_context_text = (
            build_metadata_context_text(
                facts=sql_facts,
                metadata_provider=(
                    metadata_provider
                ),
            )
        )

        llm_issues: list[
            Issue
        ] = []

        if enable_llm:
            llm_issues = (
                self.run_llm_review(
                    sql=sql,
                    file_path=file_path,
                    deterministic_issues=(
                        deterministic_issues
                    ),
                    analysis_context_text=(
                        analysis_context_text
                    ),
                    metadata_context_text=(
                        metadata_context_text
                    ),
                )
            )

        issues = self.merge_issues(
            rule_issues=(
                deterministic_issues
            ),
            llm_issues=llm_issues,
        )

        return ReviewResult(
            file_path=file_path,
            reviewed_sql=sql,
            risk_level=(
                self.calculate_risk_level(
                    issues
                )
            ),
            issue_count=len(
                issues
            ),
            issues=issues,
            analysis_result=analysis,
        )

    def run_llm_review(
        self,
        *,
        sql: str,
        file_path: str,
        deterministic_issues: list[Issue],
        analysis_context_text: str,
        metadata_context_text: str,
        query_context = None,
    ) -> list[Issue]:

        if self.llm_client is None:
            raise RuntimeError(
                "LLM review is enabled "
                "but no LLM client "
                "is configured."
            )

        reviewer = LLMReviewer(
            client=self.llm_client
        )

        return reviewer.review(
            sql=sql,
            file_path=file_path,
            guardrail_catalog_text=(
                self.rule_registry
                .build_catalog_text()
            ),
            deterministic_issues_text=(
                build_issues_text(
                    deterministic_issues
                )
            ),
            analysis_context_text=(
                analysis_context_text
            ),
            metadata_context_text=(
                metadata_context_text
            ),
            query_context=query_context,
        )


    def merge_issues(self, rule_issues: list[Issue], llm_issues: list[Issue]) -> list[Issue]:
        severity_rank = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}
        source_rank = {IssueSource.RULE: 3, IssueSource.SYSTEM: 2, IssueSource.LLM: 1}
        issues = rule_issues + llm_issues
        return sorted(
            issues,
            key=lambda issue: (-severity_rank.get(issue.severity, 0), -source_rank.get(issue.source, 0), issue.rule_id),
        )

    def calculate_risk_level(self, issues: list[Issue]) -> Severity:
        if any(issue.severity == Severity.HIGH for issue in issues):
            return Severity.HIGH
        if any(issue.severity == Severity.MEDIUM for issue in issues):
            return Severity.MEDIUM
        return Severity.LOW




