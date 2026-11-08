import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
text = Path("register/monica_register.py").read_text(encoding="utf-8")
idx = text.find("async def main")
if idx == -1:
    idx = text.find("if __name__")
print(text[idx:])
