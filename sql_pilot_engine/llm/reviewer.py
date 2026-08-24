# sql_review_agent/llm/reviewer.py

from typing import Any

from sql_pilot_engine.core.enums import IssueSource, Severity, IssueAction
from sql_pilot_engine.core.models import Issue
from sql_pilot_engine.llm.clients import BaseLLMClient
from sql_pilot_engine.llm.errors import LLMResponseValidationError
from sql_pilot_engine.llm.review_prompts import (
    LLM_REVIEW_JSON_SCHEMA,
    REPAIR_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_repair_prompt,
    build_user_prompt,
)

REQUIRED_ISSUE_FIELDS = {
    "rule_id",
    "title",
    "severity",
    "message",
    "suggestion",
    "evidence",
    "category",
    "confidence",
    "action",
    "auto_fixable",
}

class LLMReviewer:
    """LLM Review 执行器。"""

    def __init__(self, client: BaseLLMClient) -> None:
        self.client = client

    def review(
        self,
        sql: str,
        file_path: str,
        rule_catalog_text: str,
        rule_issues_text: str,
        analysis_context_text: str = "",
        metadata_context_text: str = "",
    ) -> list[Issue]:
        user_prompt = build_user_prompt(
            sql=sql,
            file_path=file_path,
            rule_catalog_text=rule_catalog_text,
            rule_issues_text=rule_issues_text,
            analysis_context_text=analysis_context_text,
            metadata_context_text=metadata_context_text,
        )

        raw_result = self.client.generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=LLM_REVIEW_JSON_SCHEMA,
        )

        try:
            return self._parse_issues(raw_result)
        except LLMResponseValidationError as first_error:
            repair_prompt = build_repair_prompt(raw_result=raw_result, error_message=str(first_error))
            repaired_result = self.client.generate_json(
                system_prompt=REPAIR_SYSTEM_PROMPT,
                user_prompt=repair_prompt,
                json_schema=LLM_REVIEW_JSON_SCHEMA,
            )
            return self._parse_issues(repaired_result)

    def _parse_issues(self, raw_result: dict[str, Any]) -> list[Issue]:
        if not isinstance(raw_result, dict):
            raise LLMResponseValidationError("LLM 返回结果必须是 JSON object。")
        if "issues" not in raw_result:
            raise LLMResponseValidationError("LLM 返回结果缺少 issues 字段。")
        if not isinstance(raw_result["issues"], list):
            raise LLMResponseValidationError("issues 必须是数组。")
        return [self._parse_single_issue(item) for item in raw_result["issues"]]

    def _parse_single_issue(self, item: dict[str, Any]) -> Issue:
        if not isinstance(item, dict):
            raise LLMResponseValidationError("LLM issue 必须是 object。")

        missing = REQUIRED_ISSUE_FIELDS - set(item.keys())
        if missing:
            raise LLMResponseValidationError(f"LLM issue 缺少字段：{sorted(missing)}")

        extra = set(item.keys()) - REQUIRED_ISSUE_FIELDS
        if extra:
            raise LLMResponseValidationError(f"LLM issue 包含多余字段：{sorted(extra)}")

        rule_id = str(item["rule_id"])
        if not rule_id.startswith("LLM_"):
            raise LLMResponseValidationError("LLM rule_id 必须以 LLM_ 开头。")

        try:
            severity = Severity(
                str(
                    item["severity"]
                ).lower()
            )
        except ValueError as error:
            raise LLMResponseValidationError(
                "severity 必须是 low、medium 或 high。"
            ) from error


        confidence = float(
            item["confidence"]
        )

        if (
            confidence < 0
            or confidence > 1
        ):
            raise LLMResponseValidationError(
                "confidence 必须在 0 到 1 之间。"
            )


        allowed_actions = {
            IssueAction.ADVISORY,
            IssueAction.AUTO_FIX,
            IssueAction.CONTEXT_REQUIRED,
            IssueAction.HUMAN_REVIEW,
        }

        try:
            action = IssueAction(
                str(
                    item["action"]
                ).lower()
            )
        except ValueError as error:
            raise LLMResponseValidationError(
                "LLM issue action 非法。"
            ) from error


        if action not in allowed_actions:
            raise LLMResponseValidationError(
                "LLM 不允许直接生成 BLOCK / IGNORE action。"
            )


        auto_fixable = bool(
            item["auto_fixable"]
        )

        if (
            action
            is IssueAction.AUTO_FIX
            and not auto_fixable
        ):
            raise LLMResponseValidationError(
                "action=auto_fix 时 "
                "auto_fixable 必须为 true。"
            )


        return Issue(
            rule_id=rule_id,
            title=str(item["title"]),
            severity=severity,
            message=str(item["message"]),
            suggestion=str(
                item["suggestion"]
            ),
            evidence=str(
                item["evidence"]
            ),
            category=str(
                item["category"]
            ),
            source=IssueSource.LLM,
            confidence=confidence,
            action=action,
            auto_fixable=auto_fixable,
        )

