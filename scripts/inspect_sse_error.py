import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("app/services/monica_client.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "Monica SSE" in l:
        print("".join(lines[max(0, i-25):min(len(lines), i+30)]))
        break