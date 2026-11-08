"""File and image upload service for Monica API."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import uuid
from typing import Any

import httpx

from app.core.exceptions import MonicaAPIException

logger = logging.getLogger(__name__)

PRESIGN_URL = "https://api.monica.im/api/file_object/pre_sign_list_by_module"
CREATE_FILE_URL = "https://api.monica.im/api/files/batch_create_llm_file"
GET_FILE_URL = "https://api.monica.im/api/files/batch_get_file"

_IMAGE_CACHE: dict[str, dict[str, Any]] = {}
MAX_IMAGE_CACHE_SIZE = 500

MIME_EXT_MAP = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/x-ms-bmp": "bmp",
    "image/svg+xml": "svg",
}


def _detect_image_type(data: bytes) -> tuple[str, str]:
    """Detect MIME type and extension from binary headers (magic numbers)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif", "gif"
    if data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data.startswith(b"BM"):
        return "image/bmp", "bmp"
    return "image/png", "png"


async def parse_image_data(
    image_source: str,
    *,
    timeout: float = 30.0,
    proxy: str | None = None,
) -> tuple[bytes, str, str]:
    """Parse image source (base64 data-URI, pure base64, or HTTP URL) into (bytes, mime, ext)."""
    image_source = image_source.strip()
    if image_source.startswith("data:"):
        # Format: data:<mime>;base64,<data>
        parts = image_source.split(",", 1)
        if len(parts) == 2:
            header, b64_str = parts
            header_lower = header.lower()
            mime_part = header_lower.replace("data:", "").split(";")[0].strip()
            mime_type = mime_part if mime_part else "image/png"
            data = base64.b64decode(b64_str.strip())
            ext = MIME_EXT_MAP.get(mime_type)
            if not ext:
                _, detected_ext = _detect_image_type(data)
                ext = detected_ext
            return data, mime_type, ext

    if image_source.startswith("http://") or image_source.startswith("https://"):
        async with httpx.AsyncClient(timeout=timeout, proxy=proxy, follow_redirects=True) as client:
            resp = await client.get(image_source)
            if resp.status_code != 200:
                raise MonicaAPIException(
                    f"Failed to fetch image from URL: {image_source} (HTTP {resp.status_code})",
                    status_code=400,
                )
            data = resp.content
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if content_type in MIME_EXT_MAP:
                mime_type = content_type
                ext = MIME_EXT_MAP[content_type]
            else:
                mime_type, ext = _detect_image_type(data)
            return data, mime_type, ext

    # Pure base64 string fallback
    try:
        data = base64.b64decode(image_source)
        mime_type, ext = _detect_image_type(data)
        return data, mime_type, ext
    except Exception as exc:
        raise MonicaAPIException(f"Invalid image format or encoding: {exc}", status_code=400) from exc


def _get_headers(
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
        "x-client-id": client_id or os.getenv("MONICA_CLIENT_ID") or str(uuid.uuid4()),
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


async def upload_image_to_monica(
    image_source: str,
    cookie: str,
    *,
    client_id: str | None = None,
    user_agent: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Upload image to Monica S3 and register LLM file object, returns FileInfo dict."""
    if not cookie:
        raise MonicaAPIException("Missing Monica cookie for image upload", status_code=401)

    proxy = (os.getenv("PROXY") or "").strip() or None
    image_bytes, mime_type, ext = await parse_image_data(image_source, timeout=timeout, proxy=proxy)

    cache_key = hashlib.sha256(image_bytes).hexdigest()
    if cache_key in _IMAGE_CACHE:
        logger.debug("Image upload cache hit: %s", cache_key[:12])
        return dict(_IMAGE_CACHE[cache_key])

    headers = _get_headers(cookie, client_id=client_id, user_agent=user_agent)
    file_name = f"{uuid.uuid4()}.{ext}"

    async with httpx.AsyncClient(timeout=timeout, proxy=proxy) as client:
        # Step 1: Pre-sign upload URL
        presign_payload = {
            "filename_list": [file_name],
            "module": "chat_bot",
            "location": "files",
            "obj_id": str(uuid.uuid4()),
        }
        try:
            resp1 = await client.post(PRESIGN_URL, json=presign_payload, headers=headers)
            if resp1.status_code != 200:
                raise MonicaAPIException(
                    f"Monica presign URL request failed: HTTP {resp1.status_code}",
                    status_code=502,
                )
            res1 = resp1.json()
            data1 = res1.get("data") or {}
            presign_urls = data1.get("pre_sign_url_list") or []
            object_urls = data1.get("object_url_list") or []
            cdn_urls = data1.get("cdn_url_list") or []
            if not presign_urls or not object_urls:
                raise MonicaAPIException(
                    f"Monica presign returned invalid payload: {res1.get('msg') or res1}",
                    status_code=502,
                )
            pre_sign_url = presign_urls[0]
            object_url = object_urls[0]
            cdn_url = cdn_urls[0] if cdn_urls else pre_sign_url.split("?")[0]
        except MonicaAPIException:
            raise
        except Exception as exc:
            raise MonicaAPIException(f"Failed to request presign URL: {exc}", status_code=502) from exc

        # Step 2: PUT image content to S3
        try:
            put_headers = {"Content-Type": mime_type}
            resp2 = await client.put(pre_sign_url, content=image_bytes, headers=put_headers)
            if resp2.status_code not in (200, 204):
                raise MonicaAPIException(
                    f"Uploading image to storage failed: HTTP {resp2.status_code}",
                    status_code=502,
                )
        except MonicaAPIException:
            raise
        except Exception as exc:
            raise MonicaAPIException(f"Failed to upload image bytes: {exc}", status_code=502) from exc

        # Step 3: Register LLM file object
        create_payload = {
            "data": [
                {
                    "file_url": cdn_url,
                    "file_uid": "",
                    "file_name": file_name,
                    "file_size": len(image_bytes),
                    "file_type": ext,
                    "file_ext": ext,
                    "object_url": object_url,
                    "parse": True,
                    "use_full_text": True,
                }
            ]
        }
        try:
            resp3 = await client.post(CREATE_FILE_URL, json=create_payload, headers=headers)
            if resp3.status_code != 200:
                raise MonicaAPIException(
                    f"Monica batch_create_llm_file failed: HTTP {resp3.status_code}",
                    status_code=502,
                )
            res3 = resp3.json()
            items = (res3.get("data") or {}).get("items") or []
            if not items:
                raise MonicaAPIException(
                    f"Monica batch_create_llm_file returned no items: {res3}",
                    status_code=502,
                )
            item = items[0]
            file_uid = item.get("file_uid") or ""
        except MonicaAPIException:
            raise
        except Exception as exc:
            raise MonicaAPIException(f"Failed to register LLM file: {exc}", status_code=502) from exc

    file_info = {
        "file_url": cdn_url,
        "file_uid": file_uid,
        "parse": True,
        "file_name": file_name,
        "file_size": len(image_bytes),
        "file_type": ext,
        "file_ext": ext,
        "file_tokens": item.get("file_tokens", 0),
        "file_chunks": item.get("file_chunks", 0),
        "object_url": None,
        "file_meta_info": {},
        "use_full_text": True,
    }

    if len(_IMAGE_CACHE) >= MAX_IMAGE_CACHE_SIZE:
        _IMAGE_CACHE.pop(next(iter(_IMAGE_CACHE)))
    _IMAGE_CACHE[cache_key] = file_info

    logger.info("Successfully uploaded image %s (uid=%s, size=%d bytes)", file_name, file_uid, len(image_bytes))
    return file_info


def extract_text_and_images(message: Any) -> tuple[str, list[str]]:
    """Extract plain text and image URLs/base64 strings from an OpenAI chat message."""
    if isinstance(message, str):
        return message, []

    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content", "")
    if content is None:
        content = message

    if isinstance(content, str):
        return content, []

    if isinstance(content, list):
        texts: list[str] = []
        image_sources: list[str] = []
        for part in content:
            if isinstance(part, dict):
                part_type = str(part.get("type") or "").lower()
                if part_type == "text":
                    texts.append(part.get("text") or "")
                elif part_type in ("image_url", "input_image", "image"):
                    img_val = part.get("image_url") or part.get("image") or part.get("url")
                    if isinstance(img_val, dict):
                        url = img_val.get("url") or img_val.get("data") or ""
                        if url:
                            image_sources.append(url)
                    elif isinstance(img_val, str) and img_val:
                        image_sources.append(img_val)
                    elif part.get("source") and isinstance(part["source"], dict):
                        src = part["source"]
                        if src.get("type") == "base64" and src.get("data"):
                            media = src.get("media_type") or "image/png"
                            image_sources.append(f"data:{media};base64,{src['data']}")
            elif isinstance(part, str):
                texts.append(part)
        return "\n".join(texts), image_sources

    return str(content or ""), []


async def resolve_message_content(
    message: Any,
    cookie: str = "",
    *,
    client_id: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Extract text and upload any images present in the message."""
    text, image_sources = extract_text_and_images(message)
    file_infos: list[dict[str, Any]] = []
    if image_sources:
        if not cookie:
            raise MonicaAPIException("Monica cookie is required to upload images", status_code=401)
        tasks = [
            upload_image_to_monica(
                src,
                cookie,
                client_id=client_id,
                user_agent=user_agent,
            )
            for src in image_sources
        ]
        file_infos = await asyncio.gather(*tasks)
    return text, file_infos
