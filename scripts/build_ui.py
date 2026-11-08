# scripts/build_ui.py
import sys
from pathlib import Path

target = Path("app/templates/dashboard.html")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("", encoding="utf-8")
print("Initialized dashboard.html")
