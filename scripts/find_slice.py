import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "slice" in l and "id" in l:
        print(f"Line {i+1}: {l.strip()}")