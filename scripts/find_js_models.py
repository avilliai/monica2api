import json
import re
import httpx

with open("scripts/home.html", "r", encoding="utf-8") as f:
    html = f.read()

scripts = re.findall(r'src="([^"]+?\.js[^"]*)"', html)
print(f"Total script tags found: {len(scripts)}")

keywords = ["GPT-6 Luna", "Luna", "DeepSeek-V4.1", "DeepSeek", "Qwen3.8", "GLM 5.3", "Flash-Lite", "Gemini 3 Flash"]

headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
client = httpx.Client(headers=headers, timeout=20, trust_env=True)

found_urls = set()
for s in scripts:
    url = ("https://monica.im" + s) if s.startswith("/") else s
    try:
        r = client.get(url)
        txt = r.text
        for kw in keywords:
            if kw.lower() in txt.lower():
                print(f"Keyword '{kw}' matched in {url}")
                idx = txt.lower().find(kw.lower())
                print("Snippet:", txt[max(0, idx - 80):min(len(txt), idx + 200)])
                found_urls.add(url)
    except Exception as e:
        pass
print("Done searching scripts. Found in:", len(found_urls))
