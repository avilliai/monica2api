import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
text = Path("app/services/monica_client.py").read_text(encoding="utf-8")
idx = text.find("def _modern_model")
print(text[idx:idx+1500])
