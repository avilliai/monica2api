import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
text = Path("register/monica_register.py").read_text(encoding="utf-8")
print(text[-1500:])
