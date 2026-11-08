with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "btn-start-register" in l or "startBatchRegister" in l:
        print(f"{i+1}: {l.strip()}")