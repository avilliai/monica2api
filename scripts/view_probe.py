import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
text = Path("app/services/cookie_manager.py").read_text(encoding="utf-8")
idx = text.find("def _probe")
print(text[idx:idx+1500])
