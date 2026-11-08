"""OpenAI 兼容视觉接口的页面状态诊断。

诊断结果只保留页面状态与置信度，不保留图像挑战的格子、坐标或点击建议。
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


ALLOWED_STATES = {
    "signup_form",
    "blocked_by_captcha",
    "otp_form",
    "signed_in",
    "form_error",
    "network_error",
    "unknown",
}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class VisionDiagnostics:
    api_base: str
    api_key: str
    model: str
    enabled: bool = False
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "VisionDiagnostics":
        api_base = (os.getenv("VISION_API_BASE") or "").rstrip("/")
        api_key = os.getenv("VISION_API_KEY") or ""
        model = os.getenv("VISION_MODEL") or "gemini-3-flash-preview"
        enabled = _env_bool("VISION_DIAGNOSTICS", False) and bool(api_base and api_key and model)
        try:
            timeout = float(os.getenv("VISION_TIMEOUT", "60"))
        except ValueError:
            timeout = 60.0
        return cls(api_base=api_base, api_key=api_key, model=model, enabled=enabled, timeout=timeout)

    async def classify_page(self, image_path: str | Path) -> dict[str, Any]:
        if not self.enabled:
            return {"state": "unknown", "confidence": 0.0, "model": self.model}

        path = Path(image_path)
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        prompt = (
            "判断这张注册页面截图当前处于哪个状态。只输出 JSON，字段为 state 和 confidence。"
            "state 只能是 signup_form、blocked_by_captcha、otp_form、signed_in、form_error、"
            "network_error、unknown 之一。不要输出验证码图片格子的选择、坐标、token 或点击步骤。"
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 120,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.api_base}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()

        raw = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = self._parse_json(raw)
        state = str(parsed.get("state", "unknown")).strip().lower()
        if state not in ALLOWED_STATES:
            state = "unknown"
        try:
            confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        return {"state": state, "confidence": confidence, "model": self.model}

    @staticmethod
    def _parse_json(raw: Any) -> dict[str, Any]:
        if isinstance(raw, list):
            raw = "".join(part.get("text", "") for part in raw if isinstance(part, dict))
        if not isinstance(raw, str):
            return {}
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*?\}", raw)
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
