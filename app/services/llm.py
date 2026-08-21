"""
LLM 服务 - 调用 smmmc OpenAI 兼容接口
只做调用, 不做业务决策. 返回结构化 JSON 或文本.
"""
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List
from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT


class LLMError(Exception):
    pass


def _post(path: str, payload: Dict[str, Any], timeout: int = LLM_TIMEOUT) -> Dict[str, Any]:
    url = f"{LLM_BASE_URL.rstrip('/')}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise LLMError(f"HTTP {e.code}: {body[:500]}")
    except Exception as e:
        raise LLMError(f"LLM request failed: {e}")


def chat(messages: List[Dict[str, str]], model: Optional[str] = None,
         temperature: float = 0.7, max_tokens: int = 4000,
         response_format: Optional[Dict[str, str]] = None) -> str:
    """普通对话, 返回 content 字符串"""
    payload = {
        "model": model or LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    r = _post("/chat/completions", payload)
    try:
        return r["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"unexpected response: {r}")


def chat_json(messages: List[Dict[str, str]], model: Optional[str] = None,
              temperature: float = 0.3, max_tokens: int = 4000,
              schema_hint: Optional[str] = None) -> Dict[str, Any]:
    """JSON 模式对话, 强制返回 JSON 对象"""
    sys_msg = "你必须只返回合法的 JSON 对象, 不要包含任何其他文字、解释或 markdown 代码块标记."
    if schema_hint:
        sys_msg += f" JSON 结构应类似于: {schema_hint}"
    full_messages = [{"role": "system", "content": sys_msg}] + messages
    content = chat(full_messages, model=model, temperature=temperature,
                   max_tokens=max_tokens,
                   response_format={"type": "json_object"})
    # 去除可能的 markdown 代码块包裹
    content = content.strip()
    if content.startswith("```"):
        # 去掉首尾的 ``` 行
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines)
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM returned invalid JSON: {e}; content preview: {content[:500]}")


def chat_text(system_prompt: str, user_prompt: str,
              model: Optional[str] = None, temperature: float = 0.7,
              max_tokens: int = 4000) -> str:
    """简单 system+user 对话"""
    return chat(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": user_prompt}],
        model=model, temperature=temperature, max_tokens=max_tokens
    )
