import httpx
import re

urls = [
    "https://assets.monica.im/home-web/_next/static/chunks/73511-7990b1cff7ec8788.js",
    "https://assets.monica.im/home-web/_next/static/chunks/18266-929740450874ed0f.js",
    "https://assets.monica.im/home-web/_next/static/chunks/75610-bfb629135e361b3c.js",
    "https://assets.monica.im/home-web/_next/static/chunks/43376-1e865fb05cb55eb7.js",
]

client = httpx.Client(timeout=20, trust_env=True)

for url in urls:
    txt = client.get(url).text
    print("=== URL:", url)
    # 查找所有的 key: "...", name: "..."
    matches = re.findall(r'key:\s*"([^"]+)",\s*name:\s*([^,\}]+)', txt)
    for k, n in matches:
        print(f"  key: {k:25} name: {n}")
    
    # 搜索包含 "gpt-6" 或 "luna" 或 "deepseek" 或 "qwen" 或 "glm" 或 "flash"
    for m in re.finditer(r'(["\'](gpt[-_]?6[^"\']*|luna[^"\']*|deepseek[^"\']*|qwen[^"\']*|glm[^"\']*|gemini[-_]?3[^"\']*)["\'])', txt, re.IGNORECASE):
        start = max(0, m.start() - 60)
        end = min(len(txt), m.end() + 100)
        print("  Context around:", m.group(0), "=>", repr(txt[start:end]))
