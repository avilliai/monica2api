import json
import re

with open("scripts/home.html", "r", encoding="utf-8") as f:
    html = f.read()

keywords = ["Luna", "DeepSeek-V4", "Flash-Lite", "Qwen3.8", "GLM 5.3", "Gemini 3 Flash", "GPT-6"]
for kw in keywords:
    pos = html.find(kw)
    if pos != -1:
        print(f"Found keyword {kw} in home.html at {pos}")
        print("Context:", html[max(0, pos-100):min(len(html), pos+200)])
    else:
        print(f"Keyword {kw} not found in home.html")
