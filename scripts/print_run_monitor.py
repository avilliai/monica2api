import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("scripts/run_and_monitor_reg.py", "r", encoding="utf-8", errors="ignore") as f:
    print(f.read())