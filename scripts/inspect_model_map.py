import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("app/services/monica_client.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "MODEL_MAP" in l:
        print("".join(lines[i:i+35]))
        break