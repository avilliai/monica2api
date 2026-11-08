with open("app/services/register.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "is_rate_limit = any(" in l:
        print("".join(lines[i:i+60]))
        break