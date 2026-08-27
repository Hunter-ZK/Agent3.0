from __future__ import annotations

import re
from typing import Any

from sql_pilot_engine.core.enums import (
    IssueAction,
    IssueSource,
    Severity,
)
from sql_pilot_engine.core.models import Issue
from sql_pilot_engine.llm.protocols import (
    StructuredGenerationModel,
)
from sql_pilot_engine.llm.errors import (
    LLMResponseValidationError,
)
from sql_pilot_engine.llm.review_prompts import (
    LLM_REVIEW_JSON_SCHEMA,
    REPAIR_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_repair_prompt,
    build_user_prompt,
)
from sql_pilot_engine.context.builder import (
    QueryContext,
)

import logging

logger = logging.getLogger(__name__)
# ============================================================
# LLM真正需要提供的字段
# ============================================================
#
# auto_fixable 不再要求 LLM 输出。
#
# 原因：
# Issue.action 才是 Trusted SQL 生命周期的唯一行为事实源。
#
# action == auto_fix
#     → auto_fixable = True
#
# 其他 action
#     → auto_fixable = False
#
# 这样可以从根源消除：
#
# advisory + auto_fixable=True
# human_review + auto_fixable=True
#
# 这类没有必要的 Contract 冲突。
# ============================================================

REQUIRED_ISSUE_FIELDS = frozenset(
    {
        "rule_id",
        "title",
        "severity",
        "message",
        "suggestion",
        "evidence",
        "category",
        "confidence",
        "action",
        "missing_context",
    }
)


ALLOWED_LLM_ACTIONS = frozenset(
    {
        IssueAction.ADVISORY,
        IssueAction.AUTO_FIX,
        IssueAction.CONTEXT_REQUIRED,
        IssueAction.HUMAN_REVIEW,
    }
)


PLACEHOLDER_RULE_IDS = {
    "LLM_EXAMPLE",
    "LLM_UNKNOWN",
    "LLM_ISSUE",
    "LLM_ISSUE_1",
    "LLM_TEST",
}


class LLMReviewer:
    """LLM SQL Review 执行器。

    职责：
    1. 调用 LLM Review；
    2. 将 LLM JSON 转换为项目 Issue；
    3. 修复可以安全确定的格式偏差；
    4. Contract 真正不可解释时触发一次 Repair。

    不负责 Workflow Routing 或 Trusted SQL 判定。
    """

    def __init__(
        self,
        client: StructuredGenerationModel,
    ) -> None:
        self.client = client

    # ========================================================
    # Public API
    # ========================================================

    def review(
        self,
        sql: str,
        file_path: str,
        guardrail_catalog_text: str,
        deterministic_issues_text: str,
        analysis_context_text: str = "",
        metadata_context_text: str = "",
        query_context: QueryContext| None = None,
    ) -> list[Issue]:

        user_prompt = build_user_prompt(
            sql=sql,
            file_path=file_path,
            guardrail_catalog_text=(
                guardrail_catalog_text
            ),
            deterministic_issues_text=(
                deterministic_issues_text
            ),
            analysis_context_text=(
                analysis_context_text
            ),
            metadata_context_text=(
                metadata_context_text
            ),
            query_context=query_context,
        )

        raw_result = self.client.generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=LLM_REVIEW_JSON_SCHEMA,
        )

        logger.debug(
            "reviewer.response\n%r",
            raw_result,
        )

        try:
            return self._parse_issues(
                raw_result
            )

        except LLMResponseValidationError as first_error:

            logger.error(
                "LLM review first parse failed. "
                "error=%s raw_result=%r",
                first_error,
                raw_result,
            )

            repair_prompt = build_repair_prompt(
                raw_result=raw_result,
                error_message=str(first_error),
            )

            repaired_result = (
                self.client.generate_json(
                    system_prompt=REPAIR_SYSTEM_PROMPT,
                    user_prompt=repair_prompt,
                    json_schema=LLM_REVIEW_JSON_SCHEMA,
                )
            )

            try:
                return self._parse_issues(
                    repaired_result
                )

            except LLMResponseValidationError as second_error:

                logger.error(
                    "LLM review repair parse failed. "
                    "first_error=%s "
                    "second_error=%s "
                    "raw_result=%r "
                    "repaired_result=%r",
                    first_error,
                    second_error,
                    raw_result,
                    repaired_result,
                )

                raise

    # ========================================================
    # Repair
    # ========================================================

    def _repair_result(
        self,
        *,
        raw_result: dict[str, Any],
        error: LLMResponseValidationError,
    ) -> dict[str, Any]:

        repair_prompt = build_repair_prompt(
            raw_result=raw_result,
            error_message=str(error),
        )

        return self.client.generate_json(
            system_prompt=REPAIR_SYSTEM_PROMPT,
            user_prompt=repair_prompt,
            json_schema=LLM_REVIEW_JSON_SCHEMA,
        )

    # ========================================================
    # Root Contract
    # ========================================================

    def _parse_issues(
        self,
        raw_result: dict[str, Any],
    ) -> list[Issue]:

        if not isinstance(
            raw_result,
            dict,
        ):
            raise LLMResponseValidationError(
                "LLM 返回结果必须是 JSON object。"
            )

        raw_issues = raw_result.get(
            "issues"
        )

        if raw_issues is None:
            raise LLMResponseValidationError(
                "LLM 返回结果缺少 issues 字段。"
            )

        if not isinstance(
            raw_issues,
            list,
        ):
            raise LLMResponseValidationError(
                "issues 必须是数组。"
            )
            


        return [
            self._parse_single_issue(
                item
            )
            for item in raw_issues
        ]

    # ========================================================
    # Single Issue
    # ========================================================

    def _parse_single_issue(
        self,
        item: Any,
    ) -> Issue:

        if not isinstance(
            item,
            dict,
        ):
            raise LLMResponseValidationError(
                "LLM issue 必须是 object。"
            )

        self._validate_required_fields(
            item
        )

        rule_id = (
            self._normalize_rule_id(
                item["rule_id"]
            )
        )

        severity = (
            self._parse_severity(
                item["severity"]
            )
        )

        confidence = (
            self._parse_confidence(
                item["confidence"]
            )
        )

        action = (
            self._normalize_action(
                item["action"]
            )
        )

        missing_context = (
            self._parse_missing_context(
                item["missing_context"]
            )
        )

        if (
            action
            is IssueAction.CONTEXT_REQUIRED
            and not missing_context
        ):
            raise LLMResponseValidationError(
                "action=context_required 时，"
                "missing_context 不能为空。"
            )

        if (
            action
            is not IssueAction.CONTEXT_REQUIRED
            and missing_context
        ):
            raise LLMResponseValidationError(
                "只有 action=context_required "
                "才能携带 missing_context。"
            )

        return Issue(
            rule_id=rule_id,
            title=self._read_text(
                item,
                "title",
            ),
            severity=severity,
            message=self._read_text(
                item,
                "message",
            ),
            suggestion=self._read_text(
                item,
                "suggestion",
                allow_empty=True,
            ),
            evidence=self._read_text(
                item,
                "evidence",
                allow_empty=True,
            ),
            category=self._read_text(
                item,
                "category",
            ),
            source=IssueSource.LLM,
            confidence=confidence,
            action=action,
            missing_context=missing_context,
            # action 是唯一事实源。
            auto_fixable=(
                action
                is IssueAction.AUTO_FIX
            ),
        )

    # ========================================================
    # Contract Validation
    # ========================================================

    @staticmethod
    def _validate_required_fields(
        item: dict[str, Any],
    ) -> None:

        missing = (
            REQUIRED_ISSUE_FIELDS
            - set(item.keys())
        )

        if missing:
            raise LLMResponseValidationError(
                "LLM issue 缺少字段："
                f"{sorted(missing)}"
            )

        # 注意：
        #
        # 不再因为 harmless extra fields
        # 直接让整个 Review 失败。
        #
        # JSON Schema 已经声明
        # additionalProperties=False。
        #
        # 如果真实模型仍然附带：
        #
        # blocking
        # auto_fixable
        # explanation
        #
        # Reviewer simply ignores them。
        #
        # 因为这些额外字段不会参与
        # Trusted SQL 行为判断。

    # ========================================================
    # rule_id
    # ========================================================

    @staticmethod
    def _normalize_rule_id(
        raw_value: Any,
    ) -> str:

        if not isinstance(
            raw_value,
            str,
        ):
            raise LLMResponseValidationError(
                "rule_id 必须是 string。"
            )

        value = raw_value.strip()

        if not value:
            raise LLMResponseValidationError(
                "rule_id 不能为空。"
            )

        # 统一成稳定内部 namespace。
        value = re.sub(
            r"[^A-Za-z0-9_]+",
            "_",
            value,
        )

        value = (
            value
            .strip("_")
            .upper()
        )

        if not value:
            raise LLMResponseValidationError(
                "rule_id 无法归一化。"
            )

        if not value.startswith(
            "LLM_"
        ):
            value = f"LLM_{value}"

        if value in PLACEHOLDER_RULE_IDS:
            raise LLMResponseValidationError(
                "rule_id 不能使用无语义占位名称。"
            )

        return value

    # ========================================================
    # Severity
    # ========================================================

    @staticmethod
    def _parse_severity(
        raw_value: Any,
    ) -> Severity:

        if not isinstance(
            raw_value,
            str,
        ):
            raise LLMResponseValidationError(
                "severity 必须是 string。"
            )

        try:
            return Severity(
                raw_value
                .strip()
                .lower()
            )

        except ValueError as error:
            raise LLMResponseValidationError(
                "severity 必须是 "
                "low、medium 或 high。"
            ) from error

    # ========================================================
    # Confidence
    # ========================================================

    @staticmethod
    def _parse_confidence(
        raw_value: Any,
    ) -> float:

        if isinstance(
            raw_value,
            bool,
        ):
            raise LLMResponseValidationError(
                "confidence 必须是 number。"
            )

        try:
            confidence = float(
                raw_value
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise LLMResponseValidationError(
                "confidence 必须是 number。"
            ) from error

        if not (
            0.0
            <= confidence
            <= 1.0
        ):
            raise LLMResponseValidationError(
                "confidence 必须在 "
                "0 到 1 之间。"
            )

        return confidence

    # ========================================================
    # Action
    # ========================================================

    @staticmethod
    def _normalize_action(
        raw_value: Any,
    ) -> IssueAction:

        if not isinstance(
            raw_value,
            str,
        ):
            raise LLMResponseValidationError(
                "action 必须是 string。"
            )

        raw_action = (
            raw_value
            .strip()
            .lower()
        )

        # ----------------------------------------------------
        # LLM 没有 BLOCK 权限。
        #
        # 但模型偶尔输出 block，
        # 这是可以安全确定性降权的：
        #
        # block → human_review
        #
        # 不赋予 LLM deterministic BLOCK 权限，
        # 同时保留它表达的高风险判断。
        # ----------------------------------------------------

        if (
            raw_action
            == IssueAction.BLOCK.value
        ):
            return (
                IssueAction
                .HUMAN_REVIEW
            )

        # ----------------------------------------------------
        # LLM 输出 ignore 同样不应该控制
        # Issue 是否被系统彻底丢弃。
        #
        # 安全降权成 advisory。
        # ----------------------------------------------------

        if (
            raw_action
            == IssueAction.IGNORE.value
        ):
            return (
                IssueAction
                .ADVISORY
            )

        try:
            action = IssueAction(
                raw_action
            )

        except ValueError as error:
            raise LLMResponseValidationError(
                f"未知的 LLM action："
                f"{raw_action!r}"
            ) from error

        if (
            action
            not in ALLOWED_LLM_ACTIONS
        ):
            raise LLMResponseValidationError(
                "LLM action 不在允许范围内。"
            )

        return action

    # ========================================================
    # Text Fields
    # ========================================================

    @staticmethod
    def _read_text(
        item: dict[str, Any],
        field_name: str,
        *,
        allow_empty: bool = False,
    ) -> str:

        value = item[
            field_name
        ]

        if not isinstance(
            value,
            str,
        ):
            raise LLMResponseValidationError(
                f"{field_name} "
                "必须是 string。"
            )

        value = value.strip()

        if (
            not allow_empty
            and not value
        ):
            raise LLMResponseValidationError(
                f"{field_name} "
                "不能为空。"
            )

        return value
        
    @staticmethod
    def _parse_missing_context(
        raw_value: Any,
    ) -> tuple[str, ...]:

        if not isinstance(
            raw_value,
            list,
        ):
            raise LLMResponseValidationError(
                "missing_context 必须是 array。"
            )

        normalized: list[str] = []

        for item in raw_value:

            if not isinstance(
                item,
                str,
            ):
                raise LLMResponseValidationError(
                    "missing_context "
                    "中的每一项必须是 string。"
                )

            value = item.strip()

            if not value:
                raise LLMResponseValidationError(
                    "missing_context "
                    "不能包含空字符串。"
                )

            if value not in normalized:
                normalized.append(value)

        return tuple(normalized)