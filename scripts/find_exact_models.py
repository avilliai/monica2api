import json
import re
import httpx

with open("scripts/home.html", "r", encoding="utf-8") as f:
    html = f.read()

scripts = re.findall(r'src="([^"]+?\.js[^"]*)"', html)

client = httpx.Client(timeout=20, trust_env=True)
keywords = [
    "gpt6Luna", "gemini35FlashLite", "gemini31FlashLite", "qwen", "glm",
    "deepseek_v4", "deepseek-v4", "gpt_6_luna", "gemini_3_5_flash_lite",
    "gemini_3_1_flash_lite", "qwen_3_8_flash", "glm_5_3_flash",
    "GPT-6 Luna", "DeepSeek-V4.1-Flash", "Gemini 3.5 Flash-Lite",
    "Qwen3.8 Flash", "GLM 5.3 Flash", "Gemini 3.1 Flash-Lite"
]

for s in scripts:
    url = ("https://monica.im" + s) if s.startswith("/") else s
    try:
        r = client.get(url)
        txt = r.text
        for kw in keywords:
            if kw.lower() in txt.lower():
                print(f"=== Keyword: '{kw}' in {url.split('/')[-1]}")
                for m in re.finditer(re.escape(kw), txt, re.IGNORECASE):
                    start = max(0, m.start() - 100)
                    end = min(len(txt), m.end() + 150)
                    print("  Snippet:", repr(txt[start:end]))
    except Exception as e:
        pass
