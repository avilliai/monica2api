with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "data.recent_logs" in l:
        print("".join(lines[max(0, i-15):min(len(lines), i+35)]))
        break