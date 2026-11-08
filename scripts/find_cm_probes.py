import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
text = Path("app/services/cookie_manager.py").read_text(encoding="utf-8")
for name in ["def _probe", "def probe", "def refresh_all", "def check"]:
    idx = 0
    while True:
        pos = text.find(name, idx)
        if pos == -1:
            break
        print(f"=== {name} at {pos} ===")
        print(text[pos:pos+400])
        idx = pos + len(name)
