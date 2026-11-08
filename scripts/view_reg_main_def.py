import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
text = Path("register/monica_register.py").read_text(encoding="utf-8")
idx = text.find("def main")
print(text[idx:idx+1500])
