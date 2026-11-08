import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
print(Path("app/app.py").read_text(encoding="utf-8"))
