import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("app/services/sse_processor.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("".join(lines[70:170]))