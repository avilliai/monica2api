import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
text = Path("app/services/cookie_manager.py").read_text(encoding="utf-8")
for name in ["get_next", "get_cookie", "get_account", "pick_account", "select_account"]:
    idx = text.find(f"def {name}")
    if idx != -1:
        print(f"Found {name} at {idx}:")
        print(text[idx:idx+800])
