"""OpenAI-compatible chat completions route with robust Function Calling support."""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import get_settings
from app.core.dependencies import get_auth_token, get_cookie_manager
from app.core.exceptions import AppException, MonicaQuotaExceededException, MonicaSafetyRefusalException, MonicaUpstreamServerException
from app.models.openai_types import ChatCompletionRequest, ChatMessage
from app.services.cookie_manager import CookieManager
from app.services.monica_client import (
    OFFICIAL_MODELS,
    convert_to_custom_bot_request,
    convert_to_monica_request,
    convert_to_web_chat_payload,
    is_supported_model,
    normalize_model_name,
    send_monica_request,
    truncate_messages,
)
from app.services.sse_processor import (
    collect_monica_sse_to_completion,
    format_safety_refusal_completion,
    format_safety_refusal_sse,
    process_monica_sse_stream,
)
from app.services.tool_calling import (
    check_truncation,
    convert_messages_with_tools,
    make_plain_response,
    make_tool_call_response,
    make_tool_call_sse,
    parse_tool_calls,
    plain_text_to_sse,
    validate_tool_call,
)

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()


def _modern_protocol() -> bool:
    return os.getenv("MONICA_WEB_PROTOCOL", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _dump_tools(tools: list[Any] | None) -> list[dict[str, Any]]:
    if not tools:
        return []
    res = []
    for t in tools:
        if hasattr(t, "model_dump"):
            res.append(t.model_dump(exclude_none=True))
        elif hasattr(t, "dict"):
            res.append(t.dict(exclude_none=True))
        elif isinstance(t, dict):
            res.append(dict(t))
    return res


def _format_tool_calling_sse_chunks(
    collected: dict[str, Any],
    model: str,
    tools: list[dict[str, Any]],
) -> list[str]:
    full_text = ""
    try:
        full_text = collected["choices"][0]["message"]["content"] or ""
    except Exception:
        full_text = ""

    # Truncation check
    is_truncated, fallback_text, next_tools = check_truncation(full_text, tools)
    if is_truncated:
        logger.warning("Tool calling output truncated, falling back to clean text before call block")
        return list(plain_text_to_sse(fallback_text, model))

    clean_text, tool_calls = parse_tool_calls(full_text)
    if tool_calls:
        # Validate arguments against schemas
        for tc in tool_calls:
            valid, missing = validate_tool_call(tc, tools)
            if not valid:
                logger.warning("Tool call %s missing params: %s", tc.get("name"), missing)
        return list(make_tool_call_sse(tool_calls, clean_text, model))
    else:
        return list(plain_text_to_sse(full_text, model))


async def _stream_chunks(chunks: list[str]) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


async def _peek_and_stream(
    stream_iter: AsyncIterator[str],
    first_chunk: str | None,
) -> AsyncIterator[str]:
    if first_chunk is not None:
        yield first_chunk
    async for chunk in stream_iter:
        yield chunk


@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    cookie_manager: CookieManager = Depends(get_cookie_manager),
    _: str = Depends(get_auth_token),
):
    settings = get_settings()
    if settings.strict_model_validation and not is_supported_model(request.model):
        raise HTTPException(
            status_code=400,
            detail=f"Model '{request.model}' is not supported. Supported models: {', '.join(OFFICIAL_MODELS)}",
        )
    # Normalize model against official 8-model whitelist; unknown models automatically fall back to gemini-3-flash
    request.model = normalize_model_name(request.model)

    if request.n != 1:
        raise HTTPException(status_code=400, detail="Only n=1 is supported")

    # Proactively truncate messages if context window limit is configured
    max_msgs = getattr(settings, "max_messages", 0)
    if isinstance(max_msgs, int) and max_msgs > 0 and len(request.messages) > max_msgs:
        orig_count = len(request.messages)
        request.messages = truncate_messages(request.messages, max_msgs)
        logger.info(
            "Proactively truncated context messages from %d to %d (MAX_MESSAGES=%d)",
            orig_count,
            len(request.messages),
            max_msgs,
        )

    tools_declarations = _dump_tools(request.tools)
    has_tools = bool(tools_declarations)

    # Pre-process messages: annotate tool descriptions & inject system prompt
    effective_messages = request.messages
    if has_tools or any(getattr(m, "role", "") == "tool" for m in request.messages):
        converted_dicts = convert_messages_with_tools(request.messages, tools_declarations if has_tools else None)
        effective_messages = [ChatMessage(**d) for d in converted_dicts]

    settings = get_settings()
    excluded: set[int] = set()
    last_error: Exception | None = None
    attempts = max(1, settings.chat_max_retries)
    for attempt in range(attempts):
        cookie = ""
        entry: dict = {}
        reserved_id: int | None = None
        try:
            if hasattr(cookie_manager, "acquire_next"):
                selected = await cookie_manager.acquire_next(excluded)
                entry = selected if isinstance(selected, dict) else {"cookie": selected}
                cookie = str(entry.get("cookie") or "")
                if entry.get("id") is not None:
                    reserved_id = int(entry["id"])
                    excluded.add(reserved_id)
            elif hasattr(cookie_manager, "get_next_entry"):
                selected = await cookie_manager.get_next_entry(excluded)
                entry = selected if isinstance(selected, dict) else {"cookie": selected}
                cookie = str(entry.get("cookie") or "")
                if entry.get("id") is not None:
                    reserved_id = int(entry["id"])
                    excluded.add(reserved_id)
            elif hasattr(cookie_manager, "get_next"):
                cookie = await cookie_manager.get_next()
            else:
                raise HTTPException(status_code=429, detail="No usable Monica account")

            if not cookie:
                raise HTTPException(status_code=429, detail="No usable Monica account")

            async def _send_and_process(target_cookie: str, target_entry: dict, raise_safety: bool):
                meta = target_entry.get("metadata") or {}
                client_id = meta.get("client_id")
                user_agent = meta.get("user_agent")

                if _modern_protocol():
                    bot_uid = (
                        settings.bot_uid
                        if (settings.custom_bot_enabled and settings.bot_uid)
                        else "monica"
                    )
                    up_req = await convert_to_web_chat_payload(
                        effective_messages,
                        request.model,
                        cookie=target_cookie,
                        client_id=client_id,
                        user_agent=user_agent,
                        bot_uid=bot_uid,
                        tools=None,
                        max_tokens=request.max_tokens,
                    )
                elif settings.custom_bot_enabled and settings.bot_uid:
                    up_req = await convert_to_custom_bot_request(
                        effective_messages,
                        request.model,
                        settings.bot_uid,
                        cookie=target_cookie,
                        client_id=client_id,
                        user_agent=user_agent,
                        tools=None,
                    )
                else:
                    up_req = await convert_to_monica_request(
                        effective_messages,
                        request.model,
                        cookie=target_cookie,
                        client_id=client_id,
                        user_agent=user_agent,
                        tools=None,
                    )

                if client_id or user_agent:
                    resp = await send_monica_request(
                        target_cookie,
                        up_req,
                        client_id=client_id,
                        user_agent=user_agent,
                    )
                else:
                    resp = await send_monica_request(target_cookie, up_req)

                if has_tools:
                    raw_res = await collect_monica_sse_to_completion(
                        resp, request.model, raise_safety_refusal=raise_safety
                    )
                    if hasattr(cookie_manager, "mark_success"):
                        await cookie_manager.mark_success(target_cookie)

                    if request.stream:
                        tool_chunks = _format_tool_calling_sse_chunks(raw_res, request.model, tools_declarations)
                        return StreamingResponse(
                            _stream_chunks(tool_chunks),
                            media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                        )

                    f_text = ""
                    try:
                        f_text = raw_res["choices"][0]["message"]["content"] or ""
                    except Exception:
                        f_text = ""
                    c_text, t_calls = parse_tool_calls(f_text)
                    if t_calls:
                        for tc in t_calls:
                            validate_tool_call(tc, tools_declarations)
                        formatted_resp = make_tool_call_response(t_calls, c_text, request.model)
                        return JSONResponse(content=formatted_resp)
                    return JSONResponse(content=raw_res)

                # No tools
                if request.stream:
                    s_iter = process_monica_sse_stream(
                        resp, request.model, raise_safety_refusal=raise_safety
                    )
                    try:
                        f_chunk = await s_iter.__anext__()
                    except StopAsyncIteration:
                        f_chunk = None

                    if hasattr(cookie_manager, "mark_success"):
                        await cookie_manager.mark_success(target_cookie)

                    return StreamingResponse(
                        _peek_and_stream(s_iter, f_chunk),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                    )

                # Plain non-stream
                raw_res = await collect_monica_sse_to_completion(
                    resp, request.model, raise_safety_refusal=raise_safety
                )
                if hasattr(cookie_manager, "mark_success"):
                    await cookie_manager.mark_success(target_cookie)
                return JSONResponse(content=raw_res)

            return await _send_and_process(cookie, entry, raise_safety=True)

        except MonicaSafetyRefusalException as safety_exc:
            refusal_text = safety_exc.message or "Sorry, I can't help with content that goes against safety guidelines."
            try:
                max_safety_retries = max(1, int(getattr(settings, "safety_max_retries", 2)))
            except (TypeError, ValueError):
                max_safety_retries = 2
            logger.warning(
                "Monica upstream returned safety guidelines refusal: %s. Automatically retrying up to %d times...",
                refusal_text[:120],
                max_safety_retries,
            )
            if cookie and hasattr(cookie_manager, "mark_success"):
                try:
                    await cookie_manager.mark_success(cookie)
                except Exception:
                    pass

            for retry_idx in range(1, max_safety_retries + 1):
                is_last_attempt = (retry_idx == max_safety_retries)
                retry_cookie = cookie
                retry_entry = entry
                try:
                    if hasattr(cookie_manager, "acquire_next"):
                        sel = await cookie_manager.acquire_next(excluded)
                        retry_entry = sel if isinstance(sel, dict) else {"cookie": sel}
                        retry_cookie = str(retry_entry.get("cookie") or "")
                    elif hasattr(cookie_manager, "get_next_entry"):
                        sel = await cookie_manager.get_next_entry(excluded)
                        retry_entry = sel if isinstance(sel, dict) else {"cookie": sel}
                        retry_cookie = str(retry_entry.get("cookie") or "")
                except Exception as acq_err:
                    logger.debug(
                        "Could not switch account for safety retry %d, reusing current: %s",
                        retry_idx,
                        acq_err,
                    )
                    retry_cookie = cookie
                    retry_entry = entry

                logger.info(
                    "Executing safety retry attempt %d/%d (account=%s)...",
                    retry_idx,
                    max_safety_retries,
                    retry_cookie[:10] if retry_cookie else "none",
                )

                try:
                    return await _send_and_process(
                        retry_cookie, retry_entry, raise_safety=(not is_last_attempt)
                    )
                except MonicaSafetyRefusalException as next_safety_exc:
                    refusal_text = next_safety_exc.message or refusal_text
                    if is_last_attempt:
                        logger.warning(
                            "Safety refusal persisted after %d retries. Returning refusal directly.",
                            max_safety_retries,
                        )
                        break
                    logger.warning(
                        "Safety refusal persisted on retry %d/%d, attempting next retry...",
                        retry_idx,
                        max_safety_retries,
                    )
                    continue
                except Exception as retry_err:
                    logger.warning(
                        "Safety refusal retry %d failed with exception: %s.",
                        retry_idx,
                        retry_err,
                    )
                    if is_last_attempt:
                        break
                    continue

            if request.stream:
                chunks = format_safety_refusal_sse(refusal_text, request.model)
                return StreamingResponse(
                    _stream_chunks(chunks),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            fallback_comp = format_safety_refusal_completion(refusal_text, request.model)
            return JSONResponse(content=fallback_comp)

        except HTTPException as exc:
            if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                await cookie_manager.release_quota(reserved_id)
            if last_error is not None and exc.status_code == 429:
                if isinstance(last_error, AppException):
                    raise last_error
                raise HTTPException(status_code=502, detail="Monica upstream request failed") from last_error
            raise
        except (MonicaQuotaExceededException, AppException) as exc:
            last_error = exc
            err_msg = str(exc)
            is_quota = (
                isinstance(exc, MonicaQuotaExceededException)
                or "10002" in err_msg
                or "quota exceeded" in err_msg.lower()
                or "insufficient quota" in err_msg.lower()
            )
            is_upstream_internal = (
                isinstance(exc, MonicaUpstreamServerException)
                or "1011" in err_msg
                or "internal server error" in err_msg.lower()
            )
            if is_quota:
                is_really_exhausted = True
                if hasattr(cookie_manager, "verify_quota_or_exhaust"):
                    try:
                        is_really_exhausted = await cookie_manager.verify_quota_or_exhaust(reserved_id or cookie, err_msg)
                    except Exception as v_err:
                        logger.warning("Failed to verify quota upstream: %s", v_err)
                        is_really_exhausted = True
                        if hasattr(cookie_manager, "mark_quota_exhausted"):
                            await cookie_manager.mark_quota_exhausted(reserved_id or cookie, err_msg)
                elif hasattr(cookie_manager, "mark_quota_exhausted"):
                    await cookie_manager.mark_quota_exhausted(reserved_id or cookie, err_msg)

                if not is_really_exhausted:
                    if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                        await cookie_manager.release_quota(reserved_id)
                    logger.warning(
                        "Monica upstream 10002 Quota exceeded, but account %s still has quota. "
                        "Request requires credits or unsupported features. Aborting retry to protect pool.",
                        reserved_id or cookie[:15],
                    )
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            "Monica upstream returned 10002 Quota exceeded: this request requires credits "
                            f"or advanced capabilities not available on standard accounts. ({err_msg})"
                        ),
                    )

                logger.warning(
                    "Monica account %s quota genuinely exhausted (10002): %s, marking exhausted and switching account (attempt %d/%d)...",
                    reserved_id or cookie[:15],
                    err_msg,
                    attempt + 1,
                    attempts,
                )
                if reserved_id is not None:
                    excluded.add(reserved_id)
                if attempt + 1 < attempts:
                    continue
                raise HTTPException(status_code=429, detail=f"All Monica accounts quota exceeded: {err_msg}") from exc
            elif is_upstream_internal:
                if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                    await cookie_manager.release_quota(reserved_id)
                logger.warning(
                    "Monica upstream internal/model error (1011): %s. "
                    "Aborting retry and skipping mark_failure to protect account pool.",
                    err_msg,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Monica upstream error (1011): {err_msg}",
                ) from exc
            else:
                if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                    await cookie_manager.release_quota(reserved_id)
                if exc.status_code < 500:
                    raise
                if cookie and hasattr(cookie_manager, "mark_failure"):
                    await cookie_manager.mark_failure(cookie, str(exc))
                if attempt + 1 >= attempts:
                    raise
        except ValueError as exc:
            if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                await cookie_manager.release_quota(reserved_id)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            last_error = exc
            err_msg = str(exc)
            is_quota = (
                "10002" in err_msg
                or "quota exceeded" in err_msg.lower()
                or "insufficient quota" in err_msg.lower()
            )
            is_upstream_internal = (
                isinstance(exc, MonicaUpstreamServerException)
                or "1011" in err_msg
                or "internal server error" in err_msg.lower()
            )
            if is_quota:
                is_really_exhausted = True
                if hasattr(cookie_manager, "verify_quota_or_exhaust"):
                    try:
                        is_really_exhausted = await cookie_manager.verify_quota_or_exhaust(reserved_id or cookie, err_msg)
                    except Exception as v_err:
                        logger.warning("Failed to verify quota upstream: %s", v_err)
                        is_really_exhausted = True
                        if hasattr(cookie_manager, "mark_quota_exhausted"):
                            await cookie_manager.mark_quota_exhausted(reserved_id or cookie, err_msg)
                elif hasattr(cookie_manager, "mark_quota_exhausted"):
                    await cookie_manager.mark_quota_exhausted(reserved_id or cookie, err_msg)

                if not is_really_exhausted:
                    if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                        await cookie_manager.release_quota(reserved_id)
                    logger.warning(
                        "Monica upstream 10002 Quota exceeded, but account %s still has quota. "
                        "Request requires credits or unsupported features. Aborting retry to protect pool.",
                        reserved_id or cookie[:15],
                    )
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            "Monica upstream returned 10002 Quota exceeded: this request requires credits "
                            f"or advanced capabilities not available on standard accounts. ({err_msg})"
                        ),
                    )

                logger.warning(
                    "Monica account %s quota genuinely exhausted (10002): %s, marking exhausted and switching account (attempt %d/%d)...",
                    reserved_id or cookie[:15],
                    err_msg,
                    attempt + 1,
                    attempts,
                )
                if reserved_id is not None:
                    excluded.add(reserved_id)
                if attempt + 1 < attempts:
                    continue
                raise HTTPException(status_code=429, detail=f"All Monica accounts quota exceeded: {err_msg}") from exc
            elif is_upstream_internal:
                if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                    await cookie_manager.release_quota(reserved_id)
                logger.warning(
                    "Monica upstream internal/model error (1011): %s. "
                    "Aborting retry and skipping mark_failure to protect account pool.",
                    err_msg,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Monica upstream error (1011): {err_msg}",
                ) from exc

            if reserved_id is not None and hasattr(cookie_manager, "release_quota"):
                await cookie_manager.release_quota(reserved_id)
            if cookie and hasattr(cookie_manager, "mark_failure"):
                await cookie_manager.mark_failure(cookie, str(exc))
            if attempt + 1 >= attempts:
                logger.exception("Monica chat request failed")
                raise HTTPException(status_code=502, detail="Monica upstream request failed") from exc

    raise HTTPException(status_code=502, detail=str(last_error or "Monica upstream request failed"))
