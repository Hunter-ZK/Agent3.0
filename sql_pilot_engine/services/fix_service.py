from dataclasses import replace

from sql_pilot_engine.core.execution_context import (
    ReviewExecutionContext,
)
from sql_pilot_engine.core.models import (
    FixedSqlResult,
    ReviewResult,
)
from sql_pilot_engine.fixing.auto_fixer import (
    generate_fixed_sql,
)
from sql_pilot_engine.llm.clients import BaseLLMClient
from sql_pilot_engine.llm.context_builder import (
    build_analysis_context_text,
    build_metadata_context_text,
)
from sql_pilot_engine.llm.fixer import LLMFixer
from sql_pilot_engine.llm.prompts import (
    build_rule_issues_text,
)
from sql_pilot_engine.services.review_service import (
    ReviewService,
)


class FixService:
    """SQL修复服务。

    负责：
    1. 对待修复SQL执行Review；
    2. 根据Issues生成自动修复；
    3. 可选调用LLM修复；
    4. 返回包含修复结果的ReviewResult。
    """

    def __init__(
        self,
        review_service: ReviewService,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.review_service = review_service
        self.llm_client = llm_client

    def fix(
        self,
        context: ReviewExecutionContext,
    ) -> ReviewResult:
        if not context.fix_sql:
            raise ValueError(
                "FixService requires fix_sql=True."
            )

        review_context = replace(
            context,
            fix_sql=False,
        )

        review_result = self.review_service.review(
            review_context
        )

        analysis_context_text = (
            build_analysis_context_text(
                sql=context.sql,
                dialect=context.dialect,
            )
        )

        metadata_context_text = (
            build_metadata_context_text(
                sql=context.sql,
                metadata_provider=(
                    context.metadata_provider
                ),
            )
        )

        fixed_sql_result = self._generate_fixed_sql(
            context=context,
            review_result=review_result,
            analysis_context_text=(
                analysis_context_text
            ),
            metadata_context_text=(
                metadata_context_text
            ),
        )

        return ReviewResult(
            file_path=review_result.file_path,
            risk_level=review_result.risk_level,
            issue_count=review_result.issue_count,
            issues=review_result.issues,
            fix_suggestions=(
                review_result.fix_suggestions
            ),
            fixed_sql_result=fixed_sql_result,
        )
    


    def _generate_fixed_sql(
        self,
        *,
        context: ReviewExecutionContext,
        review_result: ReviewResult,
        analysis_context_text: str,
        metadata_context_text: str,
    ) -> FixedSqlResult:
        auto_result = generate_fixed_sql(
            sql=context.sql,
            issues=review_result.issues,
            metadata_provider=(
                context.metadata_provider
            ),
        )

        if context.fix_provider == "auto":
            return auto_result

        if context.fix_provider != "llm":
            auto_result.manual_notes.append(
                "AI_REVIEW_TODO: "
                f"不支持的fix_provider="
                f"{context.fix_provider}，"
                "已回退到auto修复。"
            )
            return auto_result

        if self.llm_client is None:
            auto_result.manual_notes.append(
                "AI_REVIEW_TODO: "
                "fix_provider=llm，"
                "但未注入llm_client，"
                "已回退到auto修复。"
            )
            return auto_result

        rule_issues_text = build_rule_issues_text(
            review_result.issues
        )

        if context.critic_feedback:
            feedback_text = "\n".join(
                f"- {item}"
                for item in context.critic_feedback
            )

            rule_issues_text += (
                "\n\nCritic对上一轮修复的反馈：\n"
                f"{feedback_text}"
            )

        try:
            fixer = LLMFixer(
                client=self.llm_client
            )

            return fixer.fix(
                original_sql=context.sql,
                auto_fixed_sql=auto_result.fixed_sql,
                rule_issues_text=rule_issues_text,
                analysis_context_text=(
                    analysis_context_text
                ),
                metadata_context_text=(
                    metadata_context_text
                ),
            )

        except Exception as error:
            auto_result.manual_notes.append(
                "AI_REVIEW_TODO: "
                "LLM修复失败，已回退到auto修复。"
                f"错误信息：{error}"
            )
            return auto_result