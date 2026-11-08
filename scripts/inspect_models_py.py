import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("app/api/v1/models.py", "r", encoding="utf-8", errors="ignore") as f:
    print(f.read())