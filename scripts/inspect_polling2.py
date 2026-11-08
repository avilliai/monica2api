import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("".join(lines[1725:1785]))