import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.models.openai_types import ChatMessage
from app.services.monica_client import convert_to_web_chat_payload, send_web_chat_request

models_to_test = [
    ("Gemini 3 Flash", [
        ("gemini-3-flash", "gemini_3_flash"),
        ("gemini-3-flash-preview", "gemini_3_flash"),
    ]),
    ("GPT-6 Luna", [
        ("gpt-6-luna", "gpt_6_luna"),
        ("gpt-6-luna", "gpt_6_luna_chat"),
        ("gpt-6-luna", "gpt-6-luna"),
        ("gpt-6-luna", "gpt_6luna"),
    ]),
    ("DeepSeek-V4.1-Flash", [
        ("deepseek-v4.1-flash", "deepseek_v4_1_flash"),
        ("deepseek-v4.1-flash", "deepseek_v4.1_flash"),
        ("deepseek-v4.1-flash", "deepseek_v4_flash"),
        ("deepseek-v4.1-flash", "deepseek-v4.1-flash"),
        ("deepseek-v4-flash", "deepseek_v4_flash"),
    ]),
    ("Gemini 3.5 Flash-Lite", [
        ("gemini-3.5-flash-lite", "gemini_3_5_flash_lite"),
        ("gemini-3.5-flash-lite", "gemini_3.5_flash_lite"),
        ("gemini-3.5-flash-lite", "gemini-3.5-flash-lite"),
    ]),
    ("Qwen3.8 Flash", [
        ("qwen3.8-flash", "qwen_3_8_flash"),
        ("qwen-3.8-flash", "qwen_3.8_flash"),
        ("qwen-3.8-flash", "qwen-3.8-flash"),
        ("qwen3.8-flash", "qwen3_8_flash"),
    ]),
    ("GLM 5.3 Flash", [
        ("glm-5.3-flash", "glm_5_3_flash"),
        ("glm-5.3-flash", "glm_5.3_flash"),
        ("glm-5.3-flash", "glm-5.3-flash"),
        ("glm-5.3-flash", "glm5_3_flash"),
    ]),
    ("Gemini 3.1 Flash-Lite", [
        ("gemini-3.1-flash-lite", "gemini_3_1_flash_lite"),
        ("gemini-3.1-flash-lite", "gemini_3.1_flash_lite"),
        ("gemini-3.1-flash-lite", "gemini-3.1-flash-lite"),
    ]),
]

async def probe():
    with open("data/cookies.json", "r", encoding="utf-8") as f:
        cookies = json.load(f)
    cookie_str = cookies[0]["cookie"]

    results = {}
    for display_name, candidates in models_to_test:
        print(f"\n==================== Testing: {display_name} ====================")
        matched = None
        for use_m, chat_m in candidates:
            messages = [ChatMessage(role="user", content="Hi, reply with 1 word: OK")]
            try:
                # 手动构建 payload，指定 use_model 与 chat_model
                payload = await convert_to_web_chat_payload(messages, "gemini-3-flash-preview")
                payload["data"]["use_model"] = use_m
                for it in payload["data"]["items"]:
                    if it.get("item_type") == "question":
                        it["data"]["chat_model"] = chat_m
                
                stream = await send_web_chat_request(cookie_str, payload)
                text = ""
                async for line in stream.aiter_lines():
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="ignore")
                    if line.startswith("data:"):
                        try:
                            d = json.loads(line[5:].strip())
                            if "text" in d:
                                text += d["text"]
                        except Exception:
                            pass
                await stream.aclose()
                if text.strip():
                    print(f"  [SUCCESS] candidate use_model={use_m}, chat_model={chat_m} => {text.strip()[:60]}")
                    matched = (use_m, chat_m)
                    break
                else:
                    print(f"  [EMPTY] candidate use_model={use_m}, chat_model={chat_m}")
            except Exception as e:
                print(f"  [FAIL] candidate use_model={use_m}, chat_model={chat_m} => {e}")
            await asyncio.sleep(0.5)
        results[display_name] = matched

    print("\n\n==================== FINAL RESULTS ====================")
    for k, v in results.items():
        print(f"{k:25} => {v}")

asyncio.run(probe())
