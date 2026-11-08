"""将 Monica SSE 转换为 OpenAI Chat Completions 格式。"""

from __future__ import annotations

import inspect
import json
import logging
import time
from typing import Any, AsyncIterator

from app.core.exceptions import MonicaAPIException, MonicaQuotaExceededException, MonicaSafetyRefusalException, MonicaUpstreamServerException
from app.models.openai_types import ChatCompletionStreamChoice, ChatCompletionStreamResponse


logger = logging.getLogger(__name__)


def _decode_line(line: str | bytes) -> tuple[str, dict[str, Any] | None]:
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return "skip", None
    payload = stripped[5:].strip()
    if not payload:
        return "skip", None
    if payload == "[DONE]":
        return "done", None
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        logger.debug("跳过非 JSON SSE 数据: %s", payload[:300])
        return "skip", None
    return ("event", value) if isinstance(value, dict) else ("skip", None)


async def _close_upstream(response) -> None:
    close = getattr(response, "aclose", None)
    if close is None:
        close = getattr(response, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        logger.debug("关闭上游流时发生异常: %s", exc)


def _chunk(chat_id: str, created: int, model: str, delta: dict, finish_reason=None) -> str:
    value = ChatCompletionStreamResponse(
        id=f"chatcmpl-{chat_id}",
        object="chat.completion.chunk",
        created=created,
        model=model,
        choices=[
            ChatCompletionStreamChoice(
                index=0,
                delta=delta,
                finish_reason=finish_reason,
            )
        ],
    )
    return f"data: {value.model_dump_json()}\n\n"


def _format_error(err_obj: Any) -> str:
    if isinstance(err_obj, dict):
        msg = err_obj.get("message") or err_obj.get("msg") or str(err_obj)
        code = err_obj.get("code") or err_obj.get("err_code")
        return f"[{code}] {msg}" if code else str(msg)
    return str(err_obj)


def is_safety_guideline_text(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    if "goes against safety guidelines" in lower:
        return True
    if "safety guidelines" in lower and ("creative, fun, or safe ideas" in lower or "happy to help!" in lower):
        return True
    return False


def format_safety_refusal_completion(refusal_text: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-{_generate_chat_id()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": refusal_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def format_safety_refusal_sse(refusal_text: str, model: str) -> list[str]:
    chat_id = _generate_chat_id()
    created = int(time.time())
    return [
        _chunk(chat_id, created, model, {"role": "assistant", "content": refusal_text}),
        _chunk(chat_id, created, model, {}, finish_reason="stop"),
        "data: [DONE]\n\n",
    ]


def _is_safety_refusal(err_obj: Any) -> bool:
    if isinstance(err_obj, dict):
        code = str(err_obj.get("code") or err_obj.get("err_code") or "")
        msg = str(err_obj.get("msg") or err_obj.get("message") or "")
        if code in ("11121", "11120"):
            return True
        if is_safety_guideline_text(msg):
            return True
        msg_lower = msg.lower()
        if "safety guidelines" in msg_lower or "content policy" in msg_lower:
            return True
    elif isinstance(err_obj, str):
        if is_safety_guideline_text(err_obj):
            return True
        err_lower = err_obj.lower()
        if "11121" in err_lower or "safety guidelines" in err_lower:
            return True
    return False

def _extract_refusal_text(err_obj: Any) -> str:
    if isinstance(err_obj, dict):
        msg = err_obj.get("msg") or err_obj.get("message")
        if msg:
            return str(msg)
    return "Sorry, I can't help with content that goes against safety guidelines."


def _is_upstream_internal_error(err_obj: Any) -> bool:
    if isinstance(err_obj, dict):
        code = str(err_obj.get("code") or err_obj.get("err_code") or "")
        msg = str(err_obj.get("msg") or err_obj.get("message") or "").lower()
        if code in ("1011", "500", "502", "503", "504"):
            return True
        if "1011" in msg or "internal server error" in msg:
            return True
    elif isinstance(err_obj, str):
        err_lower = err_obj.lower()
        if "1011" in err_lower or "internal server error" in err_lower:
            return True
    return False


def _is_quota_exceeded(err_obj: Any) -> bool:
    if isinstance(err_obj, dict):
        code = str(err_obj.get("code") or err_obj.get("err_code") or "")
        msg = str(err_obj.get("msg") or err_obj.get("message") or "").lower()
        if code in ("10002", "10001", "10003"):
            return True
        if "quota exceeded" in msg or "insufficient quota" in msg or "purchase more" in msg:
            return True
    elif isinstance(err_obj, str):
        err_lower = err_obj.lower()
        if "10002" in err_lower or "quota exceeded" in err_lower:
            return True
    return False


async def process_monica_sse_stream(response, model: str, raise_safety_refusal: bool = False) -> AsyncIterator[str]:
    """边读取边转换，并确保请求结束或客户端断开时释放上游连接。"""
    chat_id = _generate_chat_id()
    created = int(time.time())
    think_mode = False
    role_sent = False
    completed = False

    try:
        async for line in response.aiter_lines():
            kind, event = _decode_line(line)
            if kind == "skip":
                continue
            if kind == "done":
                completed = True
                break

            if event.get("error"):
                err_obj = event.get("error")
                err_detail = _format_error(err_obj)
                if _is_safety_refusal(err_obj):
                    refusal_msg = _extract_refusal_text(err_obj)
                    logger.warning("Monica 安全策略拒绝内容: %s", refusal_msg)
                    if raise_safety_refusal:
                        raise MonicaSafetyRefusalException(
                            refusal_msg,
                            raw_error=err_obj if isinstance(err_obj, dict) else None,
                        )
                    if think_mode:
                        delta = {"content": "</think>"}
                        if not role_sent:
                            delta["role"] = "assistant"
                            role_sent = True
                        yield _chunk(chat_id, created, model, delta)
                        think_mode = False
                    delta = {"content": refusal_msg}
                    if not role_sent:
                        delta["role"] = "assistant"
                        role_sent = True
                    yield _chunk(chat_id, created, model, delta)
                    completed = True
                    break
                elif _is_quota_exceeded(err_obj):
                    logger.warning("Monica SSE 返回配额超限事件: %s", err_detail)
                    raise MonicaQuotaExceededException(f"Monica SSE 返回错误事件: {err_detail}", status_code=429)
                elif _is_upstream_internal_error(err_obj):
                    logger.warning("Monica SSE ??????/???????(1011): %s", err_detail)
                    raise MonicaUpstreamServerException(f"Monica SSE ??????: {err_detail}", status_code=502)
                else:
                    logger.error("Monica SSE 返回错误事件: %s | 原始载荷: %s", err_detail, event)
                    raise MonicaAPIException(f"Monica SSE 返回错误事件: {err_detail}", status_code=502)

            text = event.get("text") or ""
            finished = bool(event.get("finished"))
            agent_status = event.get("agent_status") or {}
            status_type = agent_status.get("type")

            if status_type == "thinking":
                if not think_mode:
                    delta = {"content": "<think>"}
                    if not role_sent:
                        delta["role"] = "assistant"
                        role_sent = True
                    yield _chunk(chat_id, created, model, delta)
                    think_mode = True
                continue

            if status_type == "thinking_detail_stream":
                detail = (agent_status.get("metadata") or {}).get("reasoning_detail") or ""
                if detail:
                    prefix = "" if think_mode else "<think>"
                    think_mode = True
                    delta = {"content": prefix + detail}
                    if not role_sent:
                        delta["role"] = "assistant"
                        role_sent = True
                    yield _chunk(chat_id, created, model, delta)
                continue

            if text:
                if raise_safety_refusal and not role_sent and is_safety_guideline_text(text):
                    logger.warning("Monica stream text safety refusal: %s", text[:200])
                    raise MonicaSafetyRefusalException(text)
                if think_mode:
                    text = "</think>" + text
                    think_mode = False
                delta = {"content": text}
                if not role_sent:
                    delta["role"] = "assistant"
                    role_sent = True
                yield _chunk(chat_id, created, model, delta)

            if finished:
                if think_mode:
                    delta = {"content": "</think>"}
                    if not role_sent:
                        delta["role"] = "assistant"
                        role_sent = True
                    yield _chunk(chat_id, created, model, delta)
                    think_mode = False
                completed = True
                break
    finally:
        await _close_upstream(response)

    if not role_sent:
        yield _chunk(chat_id, created, model, {"role": "assistant", "content": ""})
    yield _chunk(chat_id, created, model, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"
    if not completed:
        logger.debug("Monica SSE 自然结束，已补充 OpenAI 结束标记")


async def collect_monica_sse_to_completion(response, model: str, raise_safety_refusal: bool = False) -> dict:
    """收集完整 SSE，并确保非流式请求同样释放上游连接。"""
    full_content: list[str] = []
    think_mode = False

    try:
        async for line in response.aiter_lines():
            kind, event = _decode_line(line)
            if kind == "skip":
                continue
            if kind == "done":
                break
            if event.get("error"):
                err_obj = event.get("error")
                err_detail = _format_error(err_obj)
                if _is_safety_refusal(err_obj):
                    refusal_msg = _extract_refusal_text(err_obj)
                    logger.warning("Monica 安全策略拒绝内容: %s", refusal_msg)
                    if raise_safety_refusal:
                        raise MonicaSafetyRefusalException(
                            refusal_msg,
                            raw_error=err_obj if isinstance(err_obj, dict) else None,
                        )
                    full_content = [refusal_msg]
                    break
                elif _is_quota_exceeded(err_obj):
                    logger.warning("Monica SSE 返回配额超限事件: %s", err_detail)
                    raise MonicaQuotaExceededException(f"Monica SSE 返回错误事件: {err_detail}", status_code=429)
                elif _is_upstream_internal_error(err_obj):
                    logger.warning("Monica SSE ??????/???????(1011): %s", err_detail)
                    raise MonicaUpstreamServerException(f"Monica SSE ??????: {err_detail}", status_code=502)
                else:
                    logger.error("Monica SSE 返回错误事件: %s | 原始载荷: %s", err_detail, event)
                    raise MonicaAPIException(f"Monica SSE 返回错误事件: {err_detail}", status_code=502)

            text = event.get("text") or ""
            finished = bool(event.get("finished"))
            agent_status = event.get("agent_status") or {}
            status_type = agent_status.get("type")

            if status_type == "thinking":
                if not think_mode:
                    full_content.append("<think>")
                    think_mode = True
                continue
            if status_type == "thinking_detail_stream":
                detail = (agent_status.get("metadata") or {}).get("reasoning_detail") or ""
                if detail:
                    if not think_mode:
                        full_content.append("<think>")
                        think_mode = True
                    full_content.append(detail)
                continue
            if text:
                if think_mode:
                    full_content.append("</think>")
                    think_mode = False
                full_content.append(text)
            if finished:
                break
    finally:
        await _close_upstream(response)

    if think_mode:
        full_content.append("</think>")

    content_str = "".join(full_content)
    if raise_safety_refusal and is_safety_guideline_text(content_str):
        logger.warning("Monica content safety refusal: %s", content_str[:200])
        raise MonicaSafetyRefusalException(content_str)

    return {
        "id": f"chatcmpl-{_generate_chat_id()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "".join(full_content)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _generate_chat_id() -> str:
    import random
    import string

    return "".join(random.choices(string.ascii_letters + string.digits, k=29))
