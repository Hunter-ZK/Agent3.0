from dataclasses import replace

from sql_pilot_engine.core.execution_context import (
    SQLExecutionContext,
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
from sql_pilot_engine.llm.review_prompts import (
    build_issues_text,
)
from sql_pilot_engine.services.review_service import (
    ReviewService,
)
from sql_pilot_engine.analysis.sql_analysis import (
    SQLAnalysisAdapter,
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
        analysis_adapter: SQLAnalysisAdapter | None = None,
    ) -> None:
        self.review_service = review_service
        self.llm_client = llm_client
        self.analysis_adapter = analysis_adapter or SQLAnalysisAdapter()

    def fix(
        self,
        context: SQLExecutionContext,
        *,
        review_result: ReviewResult | None = None,
    ) -> ReviewResult:
        if not context.fix_sql:
            raise ValueError(
                "FixService requires fix_sql=True."
            )
        if review_result is None:
        
            review_context = replace(
                context,
                fix_sql=False,
            )

            review_result = (
                self.review_service.review(
                    review_context
                )
            )
        elif review_result.reviewed_sql != context.sql:
            # 防止SQL A的Issues被错误用于修复SQL B。
            raise ValueError(
                "The supplied review_result does not "
                "belong to the SQL being fixed."
            )

        analysis = (
            review_result.analysis_result
        )

        if analysis is None:
            analysis = (
                self.analysis_adapter.analyze(
                    sql=context.sql,
                    dialect=context.dialect,
                )
            )

        if analysis.parse_result.success and analysis.facts is not None:
            analysis_context_text = (
                build_analysis_context_text(
                    facts=analysis.facts,
                    dialect=context.dialect,
                )
            )

            metadata_context_text = (
                build_metadata_context_text(
                    facts=analysis.facts,
                    metadata_provider=(
                        context.metadata_provider
                    ),
                )
            )
        else:
            analysis_context_text = (
                "SQL 结构分析不可用。"
            )

            metadata_context_text = (
                "SQL 结构分析失败，"
                "因此未构建元数据上下文。"
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
            reviewed_sql=context.sql,
            risk_level=review_result.risk_level,
            issue_count=review_result.issue_count,
            issues=review_result.issues,
            fix_suggestions=(
                review_result.fix_suggestions
            ),
            fixed_sql_result=fixed_sql_result,
            analysis_result=analysis,
        )
    


    def _generate_fixed_sql(
        self,
        *,
        context: SQLExecutionContext,
        review_result: ReviewResult,
        analysis_context_text: str,
        metadata_context_text: str,
    ) -> FixedSqlResult:

        deterministic_result = (
            generate_fixed_sql(
                sql=context.sql,
                issues=(
                    review_result.issues
                ),
            )
        )

        if (
            context.fix_provider
            == "auto"
        ):
            return (
                deterministic_result
            )

        if (
            context.fix_provider
            != "llm"
        ):
            raise ValueError(
                "Unsupported fix_provider: "
                f"{context.fix_provider!r}"
            )

        if self.llm_client is None:
            raise RuntimeError(
                "fix_provider='llm' "
                "but no LLM client "
                "is configured."
            )

        review_issues_text = (
            build_issues_text(
                review_result.issues
            )
        )

        if context.critic_feedback:
            feedback_text = "\n".join(
                f"- {item}"
                for item
                in context.critic_feedback
            )

            review_issues_text += (
                "\n\n"
                "## Critic Feedback\n"
                f"{feedback_text}"
            )

        fixer = LLMFixer(
            client=self.llm_client
        )

        return fixer.fix(
            original_sql=context.sql,
            deterministic_pre_fix_sql=(
                deterministic_result
                .fixed_sql
            ),
            review_issues_text=(
                review_issues_text
            ),
            analysis_context_text=(
                analysis_context_text
            ),
            metadata_context_text=(
                metadata_context_text
            ),
            query_context=(
                context.query_context
            ),
        )