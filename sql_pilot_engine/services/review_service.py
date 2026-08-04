# sql_review_agent/services/review_service.py

from sql_pilot_engine.core.context import ReviewContext
from sql_pilot_engine.core.enums import IssueSource, Severity, IssueAction
from sql_pilot_engine.core.models import Issue, ReviewResult
from sql_pilot_engine.llm.clients import BaseLLMClient
from sql_pilot_engine.llm.context_builder import build_analysis_context_text, build_metadata_context_text
from sql_pilot_engine.llm.errors import LLMAPIError, LLMError, LLMResponseParseError, LLMResponseValidationError
from sql_pilot_engine.llm.prompts import build_rule_issues_text
from sql_pilot_engine.llm.reviewer import LLMReviewer
from sql_pilot_engine.rules.registry import RuleRegistry
from sql_pilot_engine.core.execution_context import ReviewExecutionContext

from sql_pilot_engine.analysis import SQLParser
from sql_pilot_engine.core.enums import IssueAction,IssueSource,Severity

from sql_pilot_engine.analysis import SQLParser
from sql_pilot_engine.analysis.facts import SQLFactsExtractor

from sql_pilot_engine.metadata.validator import MetadataValidator


class ReviewService:
    """SQL Review Agent 主编排服务。"""

    def __init__(
            self, 
            rule_registry: RuleRegistry | None = None, 
            llm_client: BaseLLMClient | None = None,
            sql_parser: SQLParser | None = None,
            facts_extractor: SQLFactsExtractor | None = None,
            metadata_validator: (MetadataValidator | None) = None,
        ) -> None:
        self.rule_registry = rule_registry or RuleRegistry()
        self.llm_client = llm_client
        self.sql_parser = sql_parser or SQLParser()
        self.facts_extractos = (facts_extractor or SQLFactsExtractor())
        
        self.metadata_validator = (metadata_validator or MetadataValidator())
        

    def review(self, context: ReviewExecutionContext) -> ReviewResult:
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
    ) -> ReviewResult:
        
        parse_result = self.sql_parser.parse(
            sql = sql,
            dialect = dialect,
        )
        
        if not parse_result.success:
            parse_issue = Issue(
                rule_id="SQL_PARSE_ERROR",
                title="SQL语法解析失败",
                severity=Severity.HIGH,
                message=(
                    parse_result.error_message
                    or "Unknown SQL parse error."
                ),
                suggestion=(
                    "请检查SQL语法及当前方言配置。"
                ),
                evidence=sql[:500],
                category="syntax",
                source=IssueSource.SYSTEM,
                confidence=1.0,
                action=IssueAction.BLOCK,
                auto_fixable=False,
                blocking=True,
                metadata={
                    "dialect": dialect,
                },
            )

            return ReviewResult(
                file_path=file_path,
                risk_level=Severity.HIGH,
                issue_count=1,
                issues=[parse_issue],
                fixed_sql_result=None,
            )
        
        sql_facts = self.facts_extractos.extract(
            parse_result=parse_result
        )
        
        context = ReviewContext(
            mode=mode,
            dialect=dialect,
            parse_result=parse_result,
            sql_facts=sql_facts,
            metadata_provider=metadata_provider,
            enable_llm=enable_llm,
            llm_provider=llm_provider,
        )

        rule_issues = self.rule_registry.run(sql=sql, context=context, categories=categories)

        analysis_context_text = build_analysis_context_text(sql=sql, dialect=dialect)
        metadata_context_text = build_metadata_context_text(sql=sql, metadata_provider=metadata_provider)

        metadata_issues: list[Issue] = []
        
        if metadata_provider is not None:
            metadata_issues = (
                self.metadata_validator.validate(
                    facts=sql_facts,
                    provider=metadata_provider,
                )
            )
        
        issues = [
            *rule_issues,
            *metadata_issues,
        ]

        llm_issues: list[Issue] = []
        if enable_llm:
            llm_issues = self.run_llm_review(
                sql=sql,
                file_path=file_path,
                rule_issues=rule_issues,
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
            )

        issues = self.merge_issues(rule_issues=issues, llm_issues=llm_issues)


        return ReviewResult(
            file_path=file_path,
            risk_level=self.calculate_risk_level(issues),
            issue_count=len(issues),
            issues=issues,
            fixed_sql_result=None,
        )

    def run_llm_review(
        self,
        sql: str,
        file_path: str,
        rule_issues: list[Issue],
        analysis_context_text: str,
        metadata_context_text: str,
    ) -> list[Issue]:
        if self.llm_client is None:
            return [
                self.build_llm_failure_issue(
                    error_type="client_missing",
                    error_message="enable_llm=True，但 ReviewService 未注入 llm_client。",
                )
            ]

        try:
            reviewer = LLMReviewer(client=self.llm_client)
            return reviewer.review(
                sql=sql,
                file_path=file_path,
                rule_catalog_text=self.rule_registry.build_catalog_text(),
                rule_issues_text=build_rule_issues_text(rule_issues),
                analysis_context_text=analysis_context_text,
                metadata_context_text=metadata_context_text,
            )
        except Exception as error:
            return [self.build_llm_failure_issue(error_type=self.get_llm_error_type(error), error_message=str(error))]


    def build_llm_failure_issue(self, error_type: str, error_message: str) -> Issue:
        return Issue(
            rule_id="LLM_REVIEW_FAILED",
            title="LLM 语义审查失败",
            severity=Severity.LOW,
            message=f"LLM 审查未完成，错误类型：{error_type}，错误信息：{error_message}",
            suggestion="请检查 LLM 配置、API Key、网络或稍后重试。规则审查结果仍然有效。",
            evidence=error_type,
            category="system",
            source=IssueSource.SYSTEM,
            confidence=1.0,
        )

    def get_llm_error_type(self, error: Exception) -> str:
        if isinstance(error, LLMAPIError):
            return "api_error"
        if isinstance(error, LLMResponseParseError):
            return "parse_error"
        if isinstance(error, LLMResponseValidationError):
            return "validation_error"
        if isinstance(error, LLMError):
            return "llm_error"
        return "unknown_error"

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
