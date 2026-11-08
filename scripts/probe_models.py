import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import httpx

with open('data/cookies.json', 'r', encoding='utf-8') as f:
    cookies = json.load(f)
c = cookies[0]
cookie_str = c['cookie']

headers = {
    'accept': '*/*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'origin': 'https://monica.im',
    'referer': 'https://monica.im/',
    'content-type': 'application/json',
    'x-client-type': 'web',
    'x-client-version': '5.4.3',
    'x-client-locale': 'zh_CN',
    'x-product-name': 'Monica',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'cookie': cookie_str,
}

client = httpx.Client(headers=headers, timeout=15, trust_env=True)

endpoints = [
    ('POST', 'https://api.monica.im/api/custom_bot/list', {}),
    ('GET', 'https://api.monica.im/api/bot/list', None),
    ('POST', 'https://api.monica.im/api/chat/models', {}),
    ('GET', 'https://api.monica.im/api/chat/models', None),
    ('POST', 'https://api.monica.im/api/usagev2/get_quotas', {'modules': ['basic_query']}),
]

for method, url, data in endpoints:
    try:
        if method == 'POST':
            resp = client.post(url, json=data)
        else:
            resp = client.get(url)
        print(f'{method} {url} -> {resp.status_code}')
        if resp.status_code == 200:
            val = resp.json()
            s = json.dumps(val, ensure_ascii=False)
            print('  response sample:', s[:300])
    except Exception as e:
        print(f'{method} {url} error: {e}')
