import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "function startJobPolling" in l or "function checkActiveRegisterJob" in l:
        print(f"--- Line {i+1} ---")
        print("".join(lines[i:i+45]))