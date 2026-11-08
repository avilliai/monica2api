import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
text = Path("app/services/monica_client.py").read_text(encoding="utf-8")
idx = text.find("def send_web_chat_request")
print(text[idx:idx+800])
