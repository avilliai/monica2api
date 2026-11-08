import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from app.core.config import get_settings, resolve_project_path

cookies_file = Path('data/cookies.json')
if cookies_file.exists():
    with open(cookies_file, 'r', encoding='utf-8') as f:
        cookies = json.load(f)
    print(f'Current cookies accounts: {len(cookies)}')
    for c in cookies:
        print(' -', c.get('email'))

settings = get_settings()
account_file = resolve_project_path(settings.outlook_account_file)
print(f'Outlook file: {account_file} exists={account_file.exists()}')
if account_file.exists():
    with open(account_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    print(f'Total outlook accounts in file: {len(lines)}')
    # 查看前 5 个
    for l in lines[:5]:
        print('sample:', l.split('----')[0] if '----' in l else l[:30])
