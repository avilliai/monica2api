with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Look for register job polling / logs in dashboard.html
for line in text.splitlines():
    if any(k in line.lower() for k in ["register/outlook/status", "recent_logs", "regstatus", "reglogs", "reglog"]):
        print(line)