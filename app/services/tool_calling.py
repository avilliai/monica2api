"""OpenAI-compatible Function Calling engine inspired by converseai2api.

Features:
- Parameter requirement auto-annotation (【必填】/【可选】 injection).
- High-adherence system prompt construction with anti-hallucination rules.
- Tool-role message normalization and auto-injection.
- Truncation detection and recovery.
- Robust JSON tool call extraction with unique call IDs.
- Standard OpenAI tool_calls format conversion for both JSON response and SSE streaming.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

_TC_BEGIN = "@@TOOL_CALL_BEGIN@@"
_TC_END = "@@TOOL_CALL_END@@"
_TC_PATTERN = re.compile(
    rf"{re.escape(_TC_BEGIN)}\s*(.*?)\s*{re.escape(_TC_END)}",
    re.DOTALL,
)


def annotate_tool_declarations(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inject 【必填】/【可选】 tags and required notices into parameter descriptions."""
    annotated = copy.deepcopy(tools)
    for tool in annotated:
        func = tool if "parameters" in tool else tool.get("function", {})
        params = func.get("parameters", {})
        required_set = set(params.get("required", []))
        props = params.get("properties", {})
        for param_name, param_def in props.items():
            tag = "【必填】" if param_name in required_set else "【可选】"
            existing = param_def.get("description", "")
            param_def["description"] = f"{tag} {existing}".strip()
        if required_set:
            params["_required_params_notice"] = (
                f"以下参数为必填，绝对不能省略或传空值：{sorted(required_set)}"
            )
    return annotated


def validate_tool_call(tc: dict[str, Any], tool_declarations: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Validate whether required parameters are present and non-empty."""
    name = tc.get("name", "")
    args = tc.get("arguments", {})
    for tool in tool_declarations:
        func = tool if "parameters" in tool else tool.get("function", {})
        func_name = func.get("name", "")
        if func_name != name:
            continue
        params = func.get("parameters", {})
        required = params.get("required", [])
        missing = [r for r in required if r not in args or args[r] in (None, "", {}, [])]
        if missing:
            logger.warning("Tool call [%s] missing required arguments: %s", name, missing)
            return False, missing
        return True, []
    logger.warning("Tool call [%s] not found in tool declarations, skipping strict validation", name)
    return True, []


def build_tool_system_prompt(tool_declarations: list[dict[str, Any]]) -> str:
    """Build high-adherence tool call prompt with strict verification rules."""
    annotated = annotate_tool_declarations(tool_declarations)
    tool_json = json.dumps(annotated, ensure_ascii=False, indent=2)
    return f"""## 核心设定：外部工具调用系统

你被赋予了调用外部真实系统（工具）的能力。当用户的需求需要真实执行（如画图、查询、搜索、计算、执行等）时，你必须精确输出工具调用代码块，而不能假装执行。

### 🚨 绝对禁止的错误模式

❌ 只演戏，不调用（没有输出 `{_TC_BEGIN}` 代码块）
❌ 假装已经拿到结果（没有真正调用工具就给出答案）
❌ 需要参数却传空对象：`"arguments": {{}}` —— 这等于没有调用！

### 🔒 调用前必须完成的自检

在输出任何 `{_TC_BEGIN}` 块之前，逐项确认：
1. 工具名称来自下方【可用工具】列表
2. 每个【必填】参数是否都有具体的、非空的值
3. 如果某个【必填】参数还不知道 → **先向用户提问，不要调用**

### ✅ 正确的调用格式

过渡语（可选）……
{_TC_BEGIN}
{{
  "name": "工具名",
  "arguments": {{
    "参数名": "参数值"
  }}
}}
{_TC_END}

**注意：**
- `{_TC_BEGIN}` 和 `{_TC_END}` 必须独占一行
- 之间只能有纯净的 JSON，不能有 Markdown 代码块标记（如 ```json）
- 输出完 `{_TC_END}` 后立即停止，等待系统返回结果
- 【必填】参数不能是空字符串 `""`、`null` 或空对象 `{{}}`

### 📌 当前【可用工具】列表

{tool_json}

### ⚠️ 系统最终警告

- 假装执行而不输出代码块 → 严重违规
- 输出代码块但【必填】参数为空或缺失 → 视同未调用，严重违规"""


def convert_messages_with_tools(
    messages: list[Any],
    tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Convert OpenAI message list for tool calling compatibility.
    
    1. Replaces 'tool' role messages with user-visible results.
    2. Injects tool system prompt into system instructions.
    """
    raw_list: list[dict[str, Any]] = []
    for msg in messages:
        if hasattr(msg, "model_dump"):
            raw_list.append(msg.model_dump(exclude_none=True))
        elif hasattr(msg, "dict"):
            raw_list.append(msg.dict(exclude_none=True))
        elif isinstance(msg, dict):
            raw_list.append(dict(msg))
        else:
            raw_list.append({"role": getattr(msg, "role", "user"), "content": getattr(msg, "content", "")})

    processed: list[dict[str, Any]] = []
    for msg in raw_list:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        name = msg.get("name") or msg.get("tool_call_id") or "tool"
        if role == "tool":
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            processed.append({
                "role": "user",
                "content": f"[工具 {name} 返回结果]\n{text}\n请基于这个结果直接回复用户，不要再次调用工具。",
            })
        else:
            processed.append({"role": role, "content": content})

    if tools:
        tool_prompt = build_tool_system_prompt(tools)
        # Find existing system message or prepend new one
        system_msg = next((m for m in processed if m.get("role") == "system"), None)
        if system_msg:
            existing = system_msg.get("content") or ""
            system_msg["content"] = f"{existing}\n\n{tool_prompt}".strip()
        else:
            processed.insert(0, {"role": "system", "content": tool_prompt})

    return processed


def parse_tool_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Extract tool call JSON objects from model output.
    
    Returns (clean_text_without_tool_blocks, list_of_tool_calls).
    """
    tool_calls: list[dict[str, Any]] = []
    for m in _TC_PATTERN.finditer(text):
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and obj.get("name"):
                tc = {
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "name": obj.get("name", ""),
                    "arguments": obj.get("arguments", {}),
                }
                tool_calls.append(tc)
                logger.info("Successfully parsed tool call: %s", tc)
        except json.JSONDecodeError:
            logger.warning("Failed to decode tool call block: %r", raw)
    clean = _TC_PATTERN.sub("", text).strip()
    return clean, tool_calls


def check_truncation(
    full_text: str, original_tools: list[dict[str, Any]]
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Detect if tool call output was truncated before completion."""
    begin_idx = full_text.find(_TC_BEGIN)
    end_idx = full_text.find(_TC_END)
    if begin_idx != -1 and end_idx == -1:
        fallback_text = full_text[:begin_idx].strip()
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', full_text[begin_idx:])
        next_tools = original_tools
        if name_match:
            target_name = name_match.group(1)
            filtered = [
                t for t in original_tools
                if t.get("name") == target_name
                or (isinstance(t.get("function"), dict) and t.get("function", {}).get("name") == target_name)
            ]
            if filtered:
                next_tools = filtered
        return True, fallback_text, next_tools
    return False, "", original_tools


def make_tool_call_response(
    tool_calls: list[dict[str, Any]],
    clean_text: str,
    model: str,
) -> dict[str, Any]:
    """Generate standard OpenAI chat completion JSON response with tool_calls."""
    openai_tool_calls = [
        {
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                if isinstance(tc["arguments"], dict)
                else str(tc["arguments"]),
            },
        }
        for tc in tool_calls
    ]
    message: dict[str, Any] = {
        "role": "assistant",
        "content": clean_text or None,
        "tool_calls": openai_tool_calls,
    }
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def make_plain_response(text: str, model: str) -> dict[str, Any]:
    """Generate standard OpenAI chat completion JSON for regular text."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def make_tool_call_sse(
    tool_calls: list[dict[str, Any]],
    clean_text: str,
    model: str,
) -> list[str]:
    """Generate standard OpenAI SSE delta chunks for tool_calls."""
    now = int(time.time())
    resp_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    def _sse(obj: dict[str, Any]) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    chunks = [
        _sse({
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
        })
    ]
    if clean_text:
        chunks.append(
            _sse({
                "id": resp_id,
                "object": "chat.completion.chunk",
                "created": now,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": clean_text}, "finish_reason": None}],
            })
        )
    openai_tool_calls_delta = [
        {
            "index": i,
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                if isinstance(tc["arguments"], dict)
                else str(tc["arguments"]),
            },
        }
        for i, tc in enumerate(tool_calls)
    ]
    chunks.append(
        _sse({
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [{"index": 0, "delta": {"tool_calls": openai_tool_calls_delta}, "finish_reason": None}],
        })
    )
    chunks.append(
        _sse({
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        })
    )
    chunks.append("data: [DONE]\n\n")
    return chunks


def plain_text_to_sse(text: str, model: str) -> list[str]:
    """Generate standard OpenAI SSE stream for plain text."""
    now = int(time.time())
    resp_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    def _sse(obj: dict[str, Any]) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    return [
        _sse({
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
        }),
        _sse({
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        }),
        _sse({
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }),
        "data: [DONE]\n\n",
    ]
