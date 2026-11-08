with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "async function registerSingleAccount" in l:
        print("".join(lines[i:i+60]))
        break