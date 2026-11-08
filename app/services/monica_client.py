"""Monica HTTP client and OpenAI-to-Monica request conversion."""

from __future__ import annotations

import inspect
import logging
import os
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    AsyncSession = None  # type: ignore[assignment]

from app.core.exceptions import MonicaAPIException
from app.models.monica_types import (
    BotData,
    BotToolData,
    CustomBotData,
    CustomBotRequest,
    DataField,
    FileInfo,
    Item,
    ItemContent,
    MonicaRequest,
    ToolData,
)
from app.services.file_service import extract_text_and_images, resolve_message_content
from app.models.openai_types import ChatMessage

logger = logging.getLogger(__name__)
BOT_CHAT_URL = "https://api.monica.im/api/custom_bot/chat"
CUSTOM_BOT_CHAT_URL = "https://api.monica.im/api/custom_bot/preview_chat"
DEFAULT_CLIENT_ID = os.getenv("MONICA_CLIENT_ID") or str(uuid.uuid4())

# 8 official free models whitelist
OFFICIAL_MODELS = [
    "gpt-6-luna",
    "deepseek-v4.1-flash",
    "gemini-3.5-flash-lite",
    "qwen3.8-flash",
    "glm-5.3-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash",
    "claude-haiku-5-5",
]

MODEL_MAP = {
    # 8 official free models
    "gpt-6-luna": "gpt-6-luna",
    "deepseek-v4.1-flash": "deepseek-v4.1-flash",
    "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "qwen3.8-flash": "qwen3.8-flash",
    "glm-5.3-flash": "glm-5.3-flash",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3-flash": "gemini-3-flash",
    "claude-haiku-5-5": "claude-haiku-5-5",

    # Aliases with dashes/dots
    "deepseek-v4-1-flash": "deepseek-v4.1-flash",
    "gemini-3-5-flash-lite": "gemini-3.5-flash-lite",
    "qwen-3.8-flash": "qwen3.8-flash",
    "qwen-3-8-flash": "qwen3.8-flash",
    "glm-5-3-flash": "glm-5.3-flash",
    "gemini-3-1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3-flash-preview": "gemini-3-flash",
}

CHAT_MODEL_MAP = {
    "gpt-6-luna": "gpt_6_luna_chat",
    "deepseek-v4.1-flash": "deepseek_v4_1_flash",
    "deepseek-v4-1-flash": "deepseek_v4_1_flash",
    "gemini-3.5-flash-lite": "gemini_3_5_flash_lite",
    "gemini-3-5-flash-lite": "gemini_3_5_flash_lite",
    "qwen3.8-flash": "qwen_3_8_flash",
    "qwen-3.8-flash": "qwen_3_8_flash",
    "qwen-3-8-flash": "qwen_3_8_flash",
    "glm-5.3-flash": "glm_5_3_flash",
    "glm-5-3-flash": "glm_5_3_flash",
    "gemini-3.1-flash-lite": "gemini_3_1_flash_lite",
    "gemini-3-1-flash-lite": "gemini_3_1_flash_lite",
    "gemini-3-flash": "gemini_3_flash",
    "gemini-3-flash-preview": "gemini_3_flash",
    "claude-haiku-5-5": "claude_haiku_5_5",
}

DEFAULT_FALLBACK_MODEL = os.getenv("DEFAULT_FALLBACK_MODEL", "gemini-3-flash")
DEFAULT_FALLBACK_CHAT_MODEL = CHAT_MODEL_MAP.get(DEFAULT_FALLBACK_MODEL, "gemini_3_flash")


def is_supported_model(model: str | None) -> bool:
    """Check if requested model is in official whitelist or known aliases."""
    if not model:
        return False
    m = model.strip()
    return m in OFFICIAL_MODELS or m in MODEL_MAP


def normalize_model_name(model: str | None) -> str:
    """Normalize requested model name against the 8 official free models whitelist.

    Any model outside the whitelist is automatically normalized to gemini-3-flash.
    """
    req = (model or "").strip()
    if not req:
        return DEFAULT_FALLBACK_MODEL
    mapped = MODEL_MAP.get(req)
    if mapped:
        return mapped
    logger.info("Model '%s' unrecognized, falling back to '%s'", req, DEFAULT_FALLBACK_MODEL)
    return DEFAULT_FALLBACK_MODEL


def _modern_model(model: str) -> tuple[str, str]:
    norm = normalize_model_name(model)
    return norm, CHAT_MODEL_MAP.get(norm, DEFAULT_FALLBACK_CHAT_MODEL)

def model_to_bot(model: str) -> str:
    _, chat_model = _modern_model(model)
    return chat_model


def _sanitize_message_text(text: str, file_infos: list[Any] | None = None) -> str:
    """Ensure message text is non-empty if no attachments, preventing upstream 1011/400 validation error."""
    if not file_infos and (not text or not str(text).strip()):
        return "..."
    return text


def _message_text(message: ChatMessage | dict[str, Any]) -> str:
    text, _ = extract_text_and_images(message)
    return text


def _validate_tools(tools: Optional[List[Dict]] = None) -> None:
    if not tools:
        return
    for t in tools:
        if not isinstance(t, dict):
            raise ValueError("Tool declarations must be dicts")


def _get_msg_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or "").lower()
    return str(getattr(msg, "role", "") or "").lower()


def truncate_messages(messages: list[Any], max_messages: int) -> list[Any]:
    """Truncate message history while keeping system prompts and trimming oldest dialogue turns.

    When max_messages > 0 and len(messages) > max_messages:
    - Retains all system instructions intact (never losing the bot persona/instructions).
    - Iteratively prunes the oldest QA pair (messages[0] and messages[1] of the dialogue history)
      until the total message count is within max_messages.
    - Guarantees at least the latest user/non-system question is kept to prevent empty prompts.
    """
    if not max_messages or max_messages <= 0 or len(messages) <= max_messages:
        return messages

    system_msgs: list[Any] = []
    non_system_msgs: list[Any] = []

    for msg in messages:
        if _get_msg_role(msg) == "system":
            system_msgs.append(msg)
        else:
            non_system_msgs.append(msg)

    if not non_system_msgs:
        return system_msgs[:max_messages] if max_messages > 0 else system_msgs

    # Keep system prompt, iteratively remove the oldest question and answer pair (history[0] & history[1])
    # until total count returns to the configured max_messages.
    while (len(system_msgs) + len(non_system_msgs)) > max_messages and len(non_system_msgs) > 1:
        if len(non_system_msgs) >= 3:
            non_system_msgs = non_system_msgs[2:]
        else:
            non_system_msgs = non_system_msgs[1:]

    return system_msgs + non_system_msgs


async def convert_to_monica_request(
    messages: List[ChatMessage],
    model: str,
    *,
    cookie: str = "",
    client_id: str | None = None,
    user_agent: str | None = None,
    bot_uid: str | None = None,
    tools: Optional[List[Dict]] = None,
) -> MonicaRequest:
    """Standard Monica API request conversion for test compatibility."""
    _validate_tools(tools)
    bot = bot_uid or model_to_bot(model)
    conv_id = f"conv:{uuid.uuid4()}"
    items: list[Item] = []
    parent_id = None
    for msg in messages:
        if getattr(msg, "role", "") == "system":
            continue
        text, file_infos = await resolve_message_content(
            msg,
            cookie=cookie,
            client_id=client_id,
            user_agent=user_agent,
        )
        text = _sanitize_message_text(text, file_infos)
        item_id = f"msg:{uuid.uuid4()}"
        item_data = ItemContent(
            type="file_with_text" if file_infos else "text",
            content=text,
            is_incognito=True,
            file_infos=[FileInfo(**fi) for fi in file_infos] if file_infos else None,
        )
        item = Item(
            conversation_id=conv_id,
            parent_item_id=parent_id,
            item_id=item_id,
            item_type="question" if getattr(msg, "role", "") == "user" else "reply",
            data=item_data,
        )
        items.append(item)
        parent_id = item_id

    return MonicaRequest(
        task_uid=f"task:{uuid.uuid4()}",
        bot_uid=bot,
        data=DataField(
            conversation_id=conv_id,
            pre_parent_item_id=parent_id or f"msg:{uuid.uuid4()}",
            items=items,
            trigger_by="auto",
            is_incognito=True,
        ),
        language="auto",
        task_type="chat",
        tool_data=ToolData(),
    )


async def convert_to_custom_bot_request(
    messages: List[ChatMessage],
    model: str,
    bot_uid: str,
    *,
    cookie: str = "",
    client_id: str | None = None,
    user_agent: str | None = None,
    tools: Optional[List[Dict]] = None,
) -> CustomBotRequest:
    """Custom bot request conversion with system prompt support."""
    _validate_tools(tools)
    _, chat_model = _modern_model(model)
    conv_id = f"conv:{uuid.uuid4()}"
    system_prompts = [_message_text(m) for m in messages if getattr(m, "role", "") == "system" and _message_text(m)]
    system_text = "\n\n".join(system_prompts).strip()

    items: list[Item] = []
    parent_id = None
    for msg in messages:
        if getattr(msg, "role", "") == "system":
            continue
        text, file_infos = await resolve_message_content(
            msg,
            cookie=cookie,
            client_id=client_id,
            user_agent=user_agent,
        )
        text = _sanitize_message_text(text, file_infos)
        item_id = f"msg:{uuid.uuid4()}"
        item_data = ItemContent(
            type="file_with_text" if file_infos else "text",
            content=text,
            is_incognito=False,
            use_model=chat_model,
            file_infos=[FileInfo(**fi) for fi in file_infos] if file_infos else None,
        )
        item = Item(
            conversation_id=conv_id,
            parent_item_id=parent_id,
            item_id=item_id,
            item_type="question" if getattr(msg, "role", "") == "user" else "reply",
            data=item_data,
        )
        items.append(item)
        parent_id = item_id

    bot_tool_data = BotToolData(use_model=chat_model)
    bot_data = BotData(
        description="Custom Bot",
        logo_url="",
        name="Assistant",
        prompt=system_text,
        uid=bot_uid,
        tool_data=bot_tool_data,
    )

    custom_data = CustomBotData(
        conversation_id=conv_id,
        items=items,
        pre_generated_reply_id=f"msg:{uuid.uuid4()}",
        pre_parent_item_id=parent_id or f"msg:{uuid.uuid4()}",
        origin="https://monica.im/home",
        origin_page_title="Monica",
        use_model=chat_model,
    )

    return CustomBotRequest(
        task_uid=f"task:{uuid.uuid4()}",
        bot_uid=bot_uid,
        data=custom_data,
        bot_data=bot_data,
    )


async def convert_to_web_chat_payload(
    messages: List[ChatMessage],
    model: str,
    *,
    cookie: str = "",
    client_id: str | None = None,
    user_agent: str | None = None,
    bot_uid: str = "monica",
    tools: Optional[List[Dict]] = None,
    max_tokens: int | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Build the modern web payload for api/custom_bot/chat."""
    _validate_tools(tools)
    locale = locale or os.getenv("MONICA_LOCALE", "zh_CN")
    use_model, chat_model = _modern_model(model)
    conversation_id = f"conv:{uuid.uuid4()}"
    welcome_id = f"msg:{uuid.uuid4()}"
    items: list[dict[str, Any]] = [
        {
            "item_id": welcome_id,
            "conversation_id": conversation_id,
            "item_type": "reply",
            "summary": "__RENDER_BOT_WELCOME_MSG__",
            "data": {"type": "text", "content": "__RENDER_BOT_WELCOME_MSG__"},
        }
    ]
    system_prompts: list[str] = [
        _message_text(m) for m in messages if getattr(m, "role", "") == "system" and _message_text(m)
    ]
    system_text = "\n\n".join(system_prompts).strip()

    parent_id = welcome_id
    first_user = True
    for message in messages:
        if getattr(message, "role", "") == "system":
            continue
        text, file_infos = await resolve_message_content(
            message,
            cookie=cookie,
            client_id=client_id,
            user_agent=user_agent,
        )
        text = _sanitize_message_text(text, file_infos)
        if getattr(message, "role", "") == "user" and first_user and system_text:
            text = f"{system_text}\n\n{text}" if text else system_text
            first_user = False
        elif getattr(message, "role", "") == "user":
            first_user = False

        item_id = f"msg:{uuid.uuid4()}"
        item_data: dict[str, Any] = {
            "type": "file_with_text" if file_infos else "text",
            "content": text,
            "quote_content": "",
            "chat_model": chat_model,
            "max_token": 0,  # Monica Web 接口若传 >0 会被识别为预分配付费 Credits 导致 10002 拒答，始终传 0
            "is_incognito": False,
        }
        if file_infos:
            item_data["file_infos"] = file_infos

        items.append(
            {
                "conversation_id": conversation_id,
                "item_id": item_id,
                "item_type": "question" if getattr(message, "role", "") == "user" else "reply",
                "summary": text or "...",
                "parent_item_id": parent_id,
                "data": item_data,
            }
        )
        parent_id = item_id

    skills = [
        {"uid": name, "enable": name == "artifacts"}
        for name in ("web_access", "draw_image", "book_calendar", "code_interpreter", "artifacts")
    ]

    return {
        "task_uid": f"task:{uuid.uuid4()}",
        "bot_uid": bot_uid,
        "data": {
            "conversation_id": conversation_id,
            "items": items,
            "pre_generated_reply_id": f"msg:{uuid.uuid4()}",
            "pre_parent_item_id": parent_id,
            "origin": os.getenv("MONICA_CHAT_ORIGIN", "https://monica.im/home"),
            "origin_page_title": os.getenv("MONICA_CHAT_TITLE", "Monica"),
            "trigger_by": "auto",
            "use_model": use_model,
            "is_incognito": False,
            "use_new_memory": True,
            "use_memory_suggestion": True,
        },
        "language": "auto",
        "locale": locale,
        "task_type": "chat_with_custom_bot",
        "tool_data": {"sys_skill_list": skills},
        "ai_resp_language": "Chinese (Simplified)",
    }


class MonicaStream:
    """Unified async line iterator and closer for httpx and curl_cffi streaming responses."""

    def __init__(self, client: Any, response: Any):
        self.client = client
        self.response = response
        self.closed = False

    async def aiter_lines(self) -> AsyncIterator[str]:
        if hasattr(self.response, "aiter_lines"):
            async for line in self.response.aiter_lines():
                yield line
        elif hasattr(self.response, "aiter_bytes"):
            buffer = b""
            async for chunk in self.response.aiter_bytes():
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    yield line.decode("utf-8", errors="replace")
            if buffer:
                yield buffer.decode("utf-8", errors="replace")

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if hasattr(self.response, "aclose"):
                await self.response.aclose()
            elif hasattr(self.response, "close"):
                res = self.response.close()
                if inspect.isawaitable(res):
                    await res
        except Exception:
            pass
        try:
            if hasattr(self.client, "aclose"):
                await self.client.aclose()
            elif hasattr(self.client, "close"):
                res = self.client.close()
                if inspect.isawaitable(res):
                    await res
        except Exception:
            pass


def _request_json(request: Any) -> dict[str, Any]:
    if isinstance(request, dict):
        return request
    dump = getattr(request, "model_dump", None)
    return dump() if dump else dict(request)


def _headers(
    cookie: str,
    *,
    client_id: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    timezone = os.getenv("MONICA_TIMEZONE", "Etc/GMT-8")
    return {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type": "application/json",
        "cookie": cookie,
        "origin": "https://monica.im",
        "referer": "https://monica.im/",
        "x-client-id": client_id or DEFAULT_CLIENT_ID,
        "x-client-locale": os.getenv("MONICA_CLIENT_LOCALE", "zh_CN"),
        "x-client-type": "web",
        "x-client-version": os.getenv("MONICA_CLIENT_VERSION", "5.4.3"),
        "x-from-channel": "NA",
        "x-product-name": "Monica",
        "x-time-zone": f"{timezone};-480",
        "user-agent": user_agent or os.getenv(
            "MONICA_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
        ),
    }


async def _open_monica_stream(
    cookie: str,
    request: Any,
    url: str,
    label: str,
    *,
    client_id: str | None = None,
    user_agent: str | None = None,
) -> MonicaStream:
    backend = os.getenv("MONICA_API_BACKEND", "httpx").strip().lower()
    headers = _headers(cookie, client_id=client_id, user_agent=user_agent)
    payload = _request_json(request)
    timeout = float(os.getenv("MONICA_TIMEOUT", "180"))
    proxy = (os.getenv("PROXY") or "").strip() or None

    if backend == "curl_cffi" and AsyncSession is not None:
        session = AsyncSession(
            impersonate=os.getenv("CURL_IMPERSONATE", "chrome131"),
            timeout=timeout,
            proxy=proxy,
        )
        try:
            response = await session.post(url, headers=headers, json=payload, stream=True)
            if response.status_code != 200:
                status = response.status_code
                await response.aclose()
                await session.close()
                raise MonicaAPIException(
                    f"{label} upstream returned HTTP {status}",
                    status_code=429 if status == 429 else (401 if status in (401, 403) else 502),
                )
            return MonicaStream(session, response)
        except MonicaAPIException:
            raise
        except Exception as exc:
            try:
                await session.close()
            except Exception:
                pass
            raise MonicaAPIException(f"{label} request failed: {exc}", status_code=502) from exc

    client = httpx.AsyncClient(timeout=timeout, proxy=proxy)
    try:
        req = client.build_request("POST", url, headers=headers, json=payload)
        response = await client.send(req, stream=True)
        if response.status_code != 200:
            status = response.status_code
            await response.aclose()
            await client.aclose()
            raise MonicaAPIException(
                f"{label} upstream returned HTTP {status}",
                status_code=429 if status == 429 else (401 if status in (401, 403) else 502),
            )
        return MonicaStream(client, response)
    except MonicaAPIException:
        raise
    except Exception as exc:
        try:
            await client.aclose()
        except Exception:
            pass
        raise MonicaAPIException(f"{label} request failed: {exc}", status_code=502) from exc


async def send_monica_request(
    cookie: str,
    request: Any,
    *,
    client_id: str | None = None,
    user_agent: str | None = None,
) -> MonicaStream:
    return await _open_monica_stream(
        cookie,
        request,
        BOT_CHAT_URL,
        "Monica API",
        client_id=client_id,
        user_agent=user_agent,
    )


async def send_custom_bot_request(cookie: str, request: Any) -> MonicaStream:
    return await _open_monica_stream(cookie, request, CUSTOM_BOT_CHAT_URL, "Custom Bot API")


async def send_web_chat_request(cookie: str, payload: dict[str, Any]) -> MonicaStream:
    return await _open_monica_stream(cookie, payload, BOT_CHAT_URL, "Monica web chat")


__all__ = [
    "BOT_CHAT_URL",
    "CUSTOM_BOT_CHAT_URL",
    "MODEL_MAP",
    "CHAT_MODEL_MAP",
    "MonicaStream",
    "convert_to_monica_request",
    "convert_to_custom_bot_request",
    "convert_to_web_chat_payload",
    "send_monica_request",
    "send_custom_bot_request",
    "send_web_chat_request",
    "model_to_bot",
    "normalize_model_name",
    "is_supported_model",
    "OFFICIAL_MODELS",
    "truncate_messages",
]
