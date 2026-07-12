# sql_review_agent/llm/errors.py

class LLMError(Exception):
    """LLM 基础异常。"""


class LLMAPIError(LLMError):
    """LLM API 调用失败。"""


class LLMResponseParseError(LLMError):
    """LLM 返回 JSON 解析失败。"""


class LLMResponseValidationError(LLMError):
    """LLM 返回结构校验失败。"""
