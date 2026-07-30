import json
from typing import Any
import re

def parse_json_object(text: str) -> dict[str, Any]:
    """从 LLM 输出中解析 JSON object。

    C-1 先做最小版本：
    - 如果 text 本身就是合法 JSON，直接解析；
    - 如果包含 ```json ... ``` 代码块，提取中间内容再解析；
    - 如果解析失败，抛 ValueError。

    C-2 再做 JSON repair。
    """

    if not isinstance(text, str):
        raise ValueError("LLM outoput must be a string")
    
    cleaned = text.strip()

    code_block_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if code_block_match:
        cleaned = code_block_match.group(1).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(f"Failed to parse JSON object: {error}") from error
        
    if not isinstance(payload, dict):
        raise ValueError("Parsed JSON must be an object")
    
    return payload