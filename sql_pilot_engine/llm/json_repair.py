from dataclasses import dataclass
from typing import Protocol


class RepairLLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...

@dataclass
class JSONRepairer:
    """使用 LLM 将非标准 JSON 输出修复为合法 JSON object 字符串。

    只负责：
    - 接收原始坏输出
    - 构造修复 prompt
    - 返回模型修复后的文本

    不负责：
    - json.loads
    - 转 SQLExplainResponse
    - Agent 路由
    """

    llm_client: RepairLLMClient

    def repair(self, broken_text: str, schema_hint: str | None = None) -> str:
        # TODO 1:
        # 1. 构造 repair prompt
        repair_prompt = self._build_repair_prompt(broken_text=broken_text, schema_hint=schema_hint)
        # 2. 调用 self.llm_client.complete(prompt)
        context = self.llm_client.complete(prompt=repair_prompt)
        # 3. 返回修复后的字符串
        return context

    def _build_repair_prompt(self, broken_text: str, schema_hint: str | None = None) -> str:
        # TODO 2:
        # 要求：
        # - 明确要求只返回合法 JSON object
        # - 不要 markdown
        # - 不要解释性文字
        # - 保留原始字段含义
        # - 如果 schema_hint 不为空，把 schema_hint 放进 prompt
        return f"""
        你是 JSON 修复器。

        请把下面内容修复为一个合法 JSON object。
        要求：
        1. 只返回 JSON object；
        2. 不要返回 markdown；
        3. 不要返回解释性文字；
        4. 不要新增无根据的业务内容；
        5. 尽量保留原始字段和值；
        6. 如果字段缺失，不要编造，使用空字符串、空数组、null 或合理默认值。

        Schema hint:
        {schema_hint or "无"}

        待修复内容：
        {broken_text}
        """.strip()