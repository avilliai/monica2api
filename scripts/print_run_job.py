with open("app/services/register.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "async def _run_job" in l:
        print("".join(lines[i:i+80]))
        break